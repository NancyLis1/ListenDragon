from __future__ import annotations

import hashlib
import json
import pickle
import re
import shutil
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from listen_dragon.services.contracts import DocumentChunk

_TERM_PATTERN = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]")


class IndexBuildError(RuntimeError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


def tokenize_for_bm25(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TERM_PATTERN.finditer(text)]


class HybridIndexBuilder:
    def __init__(
        self,
        *,
        embedding_model: str,
        model_factory: Callable[[str], Any] | None = None,
        array_factory: Callable[[Any], Any] | None = None,
        index_factory: Callable[[int], Any] | None = None,
        index_writer: Callable[[Any, str], None] | None = None,
        bm25_factory: Callable[[list[list[str]]], Any] | None = None,
    ) -> None:
        self.embedding_model = embedding_model
        self._model_factory = model_factory
        self._array_factory = array_factory
        self._index_factory = index_factory
        self._index_writer = index_writer
        self._bm25_factory = bm25_factory
        self._model: Any | None = None

    def build(self, chunks: Sequence[DocumentChunk], output_root: Path) -> Path:
        if not chunks:
            raise IndexBuildError("INDEX_EMPTY", "Cannot build an index without chunks")
        version = self._version(chunks)
        target = output_root / version
        if target.is_dir() and self._is_complete(target, version, len(chunks)):
            return target
        if target.exists():
            raise IndexBuildError(
                "INDEX_VERSION_INCOMPLETE",
                f"Index version exists without a complete manifest: {version}",
            )

        temporary = output_root / f".{version}.{uuid4().hex}.building"
        temporary.mkdir(parents=True, exist_ok=False)
        try:
            model, array_factory, index_factory, index_writer, bm25_factory = (
                self._load_dependencies()
            )
            texts = [chunk.text for chunk in chunks]
            raw_embeddings = model.encode(
                texts,
                convert_to_numpy=True,
                normalize_embeddings=True,
                show_progress_bar=False,
            )
            embeddings = array_factory(raw_embeddings)
            dimension = len(embeddings[0])
            faiss_index = index_factory(dimension)
            faiss_index.add(embeddings)
            index_writer(faiss_index, str(temporary / "faiss.index"))

            tokenized = [tokenize_for_bm25(text) for text in texts]
            bm25 = bm25_factory(tokenized)
            with (temporary / "bm25.pkl").open("wb") as stream:
                pickle.dump({"index": bm25, "chunk_ids": [c.chunk_id for c in chunks]}, stream)

            chunks_path = temporary / "chunks.jsonl"
            with chunks_path.open("w", encoding="utf-8", newline="\n") as stream:
                for chunk in chunks:
                    stream.write(json.dumps(chunk.__dict__, ensure_ascii=False) + "\n")

            manifest = {
                "index_version": version,
                "embedding_model": self.embedding_model,
                "chunk_count": len(chunks),
                "created_at": datetime.now(UTC).isoformat(),
                "files": {
                    name: self._sha256(temporary / name)
                    for name in ("faiss.index", "bm25.pkl", "chunks.jsonl")
                },
            }
            (temporary / "manifest.json").write_text(
                json.dumps(manifest, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            output_root.mkdir(parents=True, exist_ok=True)
            if target.exists():
                shutil.rmtree(temporary)
                return target
            temporary.replace(target)
            return target
        except IndexBuildError:
            raise
        except ImportError as exc:
            raise IndexBuildError(
                "INDEX_DEPENDENCY_UNAVAILABLE",
                "Install the backend ai extra before building indexes",
            ) from exc
        except Exception as exc:
            raise IndexBuildError("INDEX_BUILD_FAILED", str(exc)) from exc
        finally:
            if temporary.exists():
                shutil.rmtree(temporary)

    def _load_dependencies(self) -> tuple[Any, Callable, Callable, Callable, Callable]:
        model_factory = self._model_factory
        array_factory = self._array_factory
        index_factory = self._index_factory
        index_writer = self._index_writer
        bm25_factory = self._bm25_factory
        if model_factory is None:
            from sentence_transformers import SentenceTransformer

            model_factory = SentenceTransformer
        if array_factory is None:
            import numpy as np

            array_factory = lambda values: np.asarray(values, dtype="float32")
        if index_factory is None or index_writer is None:
            import faiss

            index_factory = index_factory or faiss.IndexFlatIP
            index_writer = index_writer or faiss.write_index
        if bm25_factory is None:
            from rank_bm25 import BM25Okapi

            bm25_factory = BM25Okapi
        if self._model is None:
            self._model = model_factory(self.embedding_model)
        return self._model, array_factory, index_factory, index_writer, bm25_factory

    def _version(self, chunks: Sequence[DocumentChunk]) -> str:
        digest = hashlib.sha256(self.embedding_model.encode())
        for chunk in chunks:
            digest.update(chunk.chunk_id.encode())
            digest.update(chunk.text.encode())
        return digest.hexdigest()[:16]

    def _is_complete(self, target: Path, version: str, chunk_count: int) -> bool:
        try:
            manifest = json.loads((target / "manifest.json").read_text(encoding="utf-8"))
            if manifest["index_version"] != version:
                return False
            if manifest["embedding_model"] != self.embedding_model:
                return False
            if manifest["chunk_count"] != chunk_count:
                return False
            expected_files = {"faiss.index", "bm25.pkl", "chunks.jsonl"}
            if set(manifest["files"]) != expected_files:
                return False
            return all(
                (target / name).is_file() and self._sha256(target / name) == manifest["files"][name]
                for name in expected_files
            )
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            return False

    @staticmethod
    def _sha256(path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
