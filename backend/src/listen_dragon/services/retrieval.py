"""T12: consume published T11 indexes and return timestamped evidence to T13."""

from __future__ import annotations

import hashlib
import json
import logging
import math
import pickle
import re
import threading
import time
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from listen_dragon.core.config import Settings
from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.indexing import tokenize_for_bm25
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url
from listen_dragon.services.contracts import DocumentChunk, RetrievedChunk
from listen_dragon.services.query_expansion import (
    ExpandedQueries,
    OpenAIQueryExpander,
    normalize_query,
)

logger = logging.getLogger(__name__)
RetrievalMode = Literal["vector", "hybrid", "multi"]


class RetrievalError(RuntimeError):
    def __init__(self, error_code: str) -> None:
        super().__init__(error_code)
        self.error_code = error_code


def reciprocal_rank_fusion(
    rankings: Sequence[Sequence[str]], *, k: int = 60,
) -> dict[str, float]:
    """One-based ranks; each item votes at most once within a result list."""
    if k < 1:
        raise ValueError("RRF k must be positive")
    scores: dict[str, float] = defaultdict(float)
    for ranking in rankings:
        unique = dict.fromkeys(ranking)
        for rank, chunk_id in enumerate(unique, start=1):
            scores[chunk_id] += 1.0 / (k + rank)
    return dict(scores)


@dataclass(frozen=True)
class SearchReport:
    video_id: str
    index_version: str
    queries: tuple[str, ...]
    chunks: tuple[RetrievedChunk, ...]
    fallback_reason: str | None
    elapsed_ms: float


class LocalHybridRetriever:
    def __init__(
        self, *, repository: SqliteJobRepository, data_root: Path,
        embedding_model: str, expander: OpenAIQueryExpander | None = None,
        top_k: int = 8, rrf_k: int = 60,
        model_factory: Callable[[str], Any] | None = None,
        index_reader: Callable[[str], Any] | None = None,
    ) -> None:
        if not 1 <= top_k <= 100 or rrf_k < 1:
            raise ValueError("Invalid retrieval parameters")
        self.repository = repository
        self.data_root = data_root.resolve()
        self.embedding_model = embedding_model
        self.expander = expander
        self.top_k = top_k
        self.rrf_k = rrf_k
        self._model_factory = model_factory
        self._index_reader = index_reader
        self._model: Any | None = None
        self._model_lock = threading.Lock()

    def search(self, video_id: str, query: str, limit: int = 6) -> Sequence[RetrievedChunk]:
        return self.search_detailed(video_id, query, limit).chunks

    def search_detailed(
        self, video_id: str, query: str, limit: int = 6, *, mode: RetrievalMode = "multi",
    ) -> SearchReport:
        started = time.perf_counter()
        try:
            identifier = UUID(video_id)
            original = normalize_query(query)
        except (ValueError, TypeError, AttributeError) as exc:
            raise RetrievalError("INVALID_QUERY") from exc
        if type(limit) is not int or not 1 <= limit <= 50 or mode not in {
            "vector", "hybrid", "multi",
        }:
            raise RetrievalError("INVALID_QUERY")

        self._require_ready(identifier)
        expanded, embeddings = self._prepare_query(original, mode)
        return self._search_prepared(
            identifier, expanded, embeddings, limit=limit, mode=mode, started=started
        )

    def search_many(
        self,
        video_ids: Sequence[str],
        query: str,
        *,
        limit_per_video: int = 6,
        mode: RetrievalMode = "multi",
    ) -> tuple[SearchReport, ...]:
        try:
            identifiers = tuple(UUID(item) for item in dict.fromkeys(video_ids))
            original = normalize_query(query)
        except (ValueError, TypeError, AttributeError) as exc:
            raise RetrievalError("INVALID_QUERY") from exc
        if not identifiers or len(identifiers) > 50 or not 1 <= limit_per_video <= 50:
            raise RetrievalError("INVALID_QUERY")
        for identifier in identifiers:
            self._require_ready(identifier)
        expanded, embeddings = self._prepare_query(original, mode)
        return tuple(
            self._search_prepared(
                identifier,
                expanded,
                embeddings,
                limit=limit_per_video,
                mode=mode,
                started=time.perf_counter(),
            )
            for identifier in identifiers
        )

    def _prepare_query(self, original: str, mode: RetrievalMode) -> tuple[ExpandedQueries, Any]:
        if mode not in {"vector", "hybrid", "multi"}:
            raise RetrievalError("INVALID_QUERY")
        expanded = ExpandedQueries((original,), "disabled")
        if mode == "multi" and self.expander is not None:
            expanded = self.expander.expand(original)
        return expanded, self._encode(expanded.queries)

    def _search_prepared(
        self,
        identifier: UUID,
        expanded: ExpandedQueries,
        embeddings: Any,
        *,
        limit: int,
        mode: RetrievalMode,
        started: float,
    ) -> SearchReport:
        self._require_ready(identifier)
        job = self.repository.get_video_job(identifier)
        assert job is not None

        try:
            version = self.repository.get_chunk_index_version(identifier)
        except ValueError as exc:
            raise RetrievalError("INDEX_VERSION_MISMATCH") from exc
        if version is None:
            raise RetrievalError("INDEX_NOT_FOUND")

        chunks, vector_index, bm25 = self._load_index(identifier, version)
        if embeddings.ndim != 2 or embeddings.shape[1] != vector_index.d:
            raise RetrievalError("EMBEDDING_DIMENSION_MISMATCH")
        rankings: list[list[str]] = []
        try:
            distances, positions = vector_index.search(embeddings, min(self.top_k, len(chunks)))
            for query_index, rewritten in enumerate(expanded.queries):
                vector_rank = []
                for distance, position in zip(
                    distances[query_index], positions[query_index], strict=True,
                ):
                    position = int(position)
                    if position == -1:
                        continue
                    if position < 0 or position >= len(chunks) or not math.isfinite(float(distance)):
                        raise RetrievalError("INDEX_CORRUPT")
                    vector_rank.append(chunks[position].chunk_id)
                rankings.append(vector_rank)
                if mode != "vector":
                    tokens = tokenize_for_bm25(rewritten)
                    scores = bm25.get_scores(tokens)
                    if len(scores) != len(chunks):
                        raise RetrievalError("INDEX_CORRUPT")
                    # BM25 scores may legitimately be zero/negative on small corpora.
                    # Exclude no-overlap documents, not all nonpositive scores.
                    token_set = set(tokens)
                    matches = []
                    for i, chunk in enumerate(chunks):
                        score = float(scores[i])
                        if not math.isfinite(score):
                            raise RetrievalError("INDEX_CORRUPT")
                        if token_set.intersection(tokenize_for_bm25(chunk.text)):
                            matches.append(i)
                    matches.sort(key=lambda i: (-float(scores[i]), i))
                    rankings.append([chunks[i].chunk_id for i in matches[:self.top_k]])
        except RetrievalError:
            raise
        except Exception as exc:
            raise RetrievalError("RETRIEVAL_FAILED") from exc

        scores = reciprocal_rank_fusion(rankings, k=self.rrf_k)
        by_id = {chunk.chunk_id: chunk for chunk in chunks}
        ordered = sorted(scores, key=lambda key: (-scores[key], by_id[key].start_ms, key))
        results = tuple(
            RetrievedChunk(key, by_id[key].start_ms, by_id[key].end_ms, by_id[key].text, scores[key])
            for key in ordered[:limit]
        )
        elapsed = (time.perf_counter() - started) * 1000
        logger.info(
            "retrieval_finished video_id=%s index_version=%s query_count=%d "
            "result_count=%d fallback=%s duration_ms=%.1f",
            identifier, version, len(expanded.queries), len(results),
            expanded.fallback_reason or "none", elapsed,
        )
        return SearchReport(
            str(identifier), version, expanded.queries, results, expanded.fallback_reason, elapsed,
        )

    def _require_ready(self, identifier: UUID) -> None:
        job = self.repository.get_video_job(identifier)
        if job is None:
            raise RetrievalError("VIDEO_NOT_FOUND")
        if job.state is not JobState.ready:
            raise RetrievalError("VIDEO_NOT_READY")

    def _load_index(self, video_id: UUID, version: str) -> tuple[list[DocumentChunk], Any, Any]:
        if not re.fullmatch(r"[0-9a-f]{16}", version):
            raise RetrievalError("INDEX_VERSION_MISMATCH")
        root = self.data_root / "indexes" / str(video_id) / version
        if not root.exists():
            raise RetrievalError("INDEX_NOT_FOUND")
        if root.is_symlink() or not root.resolve().is_relative_to(self.data_root):
            raise RetrievalError("INDEX_CORRUPT")
        names = {"faiss.index", "bm25.pkl", "chunks.jsonl"}
        try:
            for name in names | {"manifest.json"}:
                path = root / name
                if not path.is_file() or path.is_symlink():
                    raise RetrievalError("INDEX_CORRUPT")
            manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
            if manifest["index_version"] != version:
                raise RetrievalError("INDEX_VERSION_MISMATCH")
            if manifest["embedding_model"] != self.embedding_model:
                raise RetrievalError("EMBEDDING_MODEL_MISMATCH")
            if set(manifest["files"]) != names:
                raise RetrievalError("INDEX_CORRUPT")
            for name in names:
                with (root / name).open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                if digest != manifest["files"][name]:
                    raise RetrievalError("INDEX_CORRUPT")
            chunks = [
                DocumentChunk(**json.loads(line))
                for line in (root / "chunks.jsonl").read_text(encoding="utf-8").splitlines()
            ]
            if not chunks or len(chunks) != manifest["chunk_count"]:
                raise RetrievalError("INDEX_CORRUPT")
            ids = [chunk.chunk_id for chunk in chunks]
            if len(ids) != len(set(ids)):
                raise RetrievalError("INDEX_CORRUPT")
            if any(
                type(c.start_ms) is not int or type(c.end_ms) is not int
                or c.start_ms < 0 or c.start_ms >= c.end_ms
                or not isinstance(c.text, str) or not c.text.strip()
                for c in chunks
            ):
                raise RetrievalError("INDEX_CORRUPT")
            database_chunks = self.repository.list_chunks(video_id)
            if {c.chunk_id: c for c in database_chunks} != {c.chunk_id: c for c in chunks}:
                raise RetrievalError("INDEX_VERSION_MISMATCH")
            # Only locally generated, operator-controlled artifacts are trusted.
            # Checksums detect corruption; they do NOT make arbitrary pickle safe.
            with (root / "bm25.pkl").open("rb") as stream:
                sparse = pickle.load(stream)
            if sparse["chunk_ids"] != ids or sparse["index"].corpus_size != len(chunks):
                raise RetrievalError("INDEX_CORRUPT")
            reader = self._index_reader
            if reader is None:
                import faiss

                reader = faiss.read_index
            dense = reader(str(root / "faiss.index"))
            if dense.ntotal != len(chunks) or dense.metric_type != 0 or dense.d < 1:
                raise RetrievalError("INDEX_CORRUPT")
            return chunks, dense, sparse["index"]
        except RetrievalError:
            raise
        except ImportError as exc:
            raise RetrievalError("RETRIEVAL_DEPENDENCY_UNAVAILABLE") from exc
        except Exception as exc:
            raise RetrievalError("INDEX_CORRUPT") from exc

    def _encode(self, queries: Sequence[str]) -> Any:
        try:
            import numpy as np

            with self._model_lock:
                if self._model is None:
                    factory = self._model_factory
                    if factory is None:
                        from sentence_transformers import SentenceTransformer

                        factory = SentenceTransformer
                    self._model = factory(self.embedding_model)
                embeddings = np.asarray(self._model.encode(
                    list(queries), normalize_embeddings=True, convert_to_numpy=True,
                    show_progress_bar=False,
                ), dtype="float32")
            if embeddings.ndim != 2 or embeddings.shape[0] != len(queries):
                raise RetrievalError("EMBEDDING_DIMENSION_MISMATCH")
            if not np.isfinite(embeddings).all():
                raise RetrievalError("EMBEDDING_FAILED")
            return np.ascontiguousarray(embeddings)
        except RetrievalError:
            raise
        except ImportError as exc:
            raise RetrievalError("RETRIEVAL_DEPENDENCY_UNAVAILABLE") from exc
        except Exception as exc:
            raise RetrievalError("EMBEDDING_FAILED") from exc


def build_retriever(settings: Settings) -> LocalHybridRetriever:
    repository = SqliteJobRepository(sqlite_path_from_url(settings.database_url))
    repository.initialize()
    return LocalHybridRetriever(
        repository=repository, data_root=Path(settings.data_root),
        embedding_model=settings.embedding_model,
        top_k=settings.retrieval_top_k, rrf_k=settings.retrieval_rrf_k,
        expander=OpenAIQueryExpander(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key,
            model=settings.llm_model, enabled=settings.query_expansion_enabled,
            timeout_seconds=settings.query_expansion_timeout_seconds,
        ),
    )
