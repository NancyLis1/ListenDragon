import hashlib
import json
import sqlite3
from pathlib import Path
from uuid import uuid4

import numpy as np
import pytest

from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.indexing import HybridIndexBuilder
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.contracts import DocumentChunk
from listen_dragon.services.query_expansion import ExpandedQueries
from listen_dragon.services.retrieval import (
    LocalHybridRetriever,
    RetrievalError,
    reciprocal_rank_fusion,
)


class SparseIndex:
    def __init__(self, tokens):
        self.corpus_size = len(tokens)

    def get_scores(self, tokens):
        # All-zero scores are legitimate for very small BM25 corpora.
        return [0.0] * self.corpus_size


class DenseIndex:
    def __init__(self, dimension):
        self.d = dimension
        self.metric_type = 0
        self.ntotal = 0

    def add(self, embeddings):
        self.ntotal = len(embeddings)

    def search(self, embeddings, k):
        return np.ones((len(embeddings), k)), np.tile(list(range(k)), (len(embeddings), 1))


class Encoder:
    def encode(self, texts, **kwargs):
        assert kwargs["normalize_embeddings"] is True
        return [[1.0, 0.0] for _ in texts]


@pytest.fixture
def published(tmp_path):
    repository = SqliteJobRepository(tmp_path / "jobs.db")
    repository.initialize()
    dense = DenseIndex(2)

    def publish(prefix):
        video_id = uuid4()
        repository.create_video_job(
            video_id=video_id, original_name="test.mp4", mime="video/mp4", size_bytes=1,
            sha256="fixture", source_path=tmp_path / "test.mp4",
        )
        chunks = [
            DocumentChunk(prefix + "-1", 0, 1000, "Python 环境安装", 8),
            DocumentChunk(prefix + "-2", 1000, 2500, "课题分离由承担后果的人决定", 13),
            DocumentChunk(prefix + "-3", 2500, 4000, "人人是伙伴，不需要战胜别人", 13),
        ]
        repository.replace_chunks(video_id, chunks)
        builder = HybridIndexBuilder(
            embedding_model="test-model", model_factory=lambda _: Encoder(),
            array_factory=lambda values: values, index_factory=lambda _: dense,
            index_writer=lambda _, path: Path(path).write_bytes(b"fixture-index"),
            bm25_factory=SparseIndex,
        )
        root = builder.build(chunks, tmp_path / "indexes" / str(video_id))
        repository.set_chunk_index_version(video_id, root.name)
        repository.update_job(video_id, state=JobState.ready, progress=100)
        return video_id, chunks, root

    first = publish("first")
    second = publish("second")
    retriever = LocalHybridRetriever(
        repository=repository, data_root=tmp_path, embedding_model="test-model",
        model_factory=lambda _: Encoder(), index_reader=lambda _: dense,
    )
    return retriever, first, second, dense


def test_rrf_uses_one_based_rank_and_deduplicates_each_list():
    scores = reciprocal_rank_fusion([["a", "a", "b"], ["b", "c"]], k=60)
    assert scores == pytest.approx({"a": 1 / 61, "b": 1 / 62 + 1 / 61, "c": 1 / 62})
    assert reciprocal_rank_fusion([]) == {}
    with pytest.raises(ValueError):
        reciprocal_rank_fusion([["a"]], k=0)


def test_hybrid_keeps_zero_bm25_matches_and_exact_timestamps(published):
    retriever, (video_id, chunks, root), _, _ = published
    report = retriever.search_detailed(str(video_id), "课题分离", 2, mode="hybrid")
    assert report.chunks[0].chunk_id == "first-2"
    assert report.index_version == root.name
    assert report.chunks[0].start_ms == chunks[1].start_ms
    assert report.chunks[0].end_ms == chunks[1].end_ms
    assert report.chunks[0].text == chunks[1].text
    assert len(report.chunks) == 2


def test_video_isolation_and_no_duplicate_results(published):
    retriever, first, second, _ = published
    for video, prefix in [(first, "first"), (second, "second")]:
        results = retriever.search(str(video[0]), "课题分离")
        assert all(row.chunk_id.startswith(prefix) for row in results)
        assert len({row.chunk_id for row in results}) == len(results)


def test_multiquery_expansion_is_consumed(published):
    retriever, first, _, _ = published

    class Expander:
        def expand(self, query):
            return ExpandedQueries((query, "课题分离", "承担后果"))

    retriever.expander = Expander()
    report = retriever.search_detailed(str(first[0]), "谁负责")
    assert len(report.queries) == 3
    assert report.chunks[0].chunk_id == "first-2"


def test_search_many_expands_and_encodes_query_once(published):
    retriever, first, second, _ = published
    calls = {"expand": 0, "encode": 0}

    class Expander:
        def expand(self, query):
            calls["expand"] += 1
            return ExpandedQueries((query, "课题分离"))

    class CountingEncoder:
        def encode(self, texts, **kwargs):
            calls["encode"] += 1
            return [[1.0, 0.0] for _ in texts]

    retriever.expander = Expander()
    retriever._model = CountingEncoder()
    reports = retriever.search_many([str(first[0]), str(second[0])], "谁负责")

    assert len(reports) == 2
    assert calls == {"expand": 1, "encode": 1}


@pytest.mark.parametrize("query,limit", [("", 6), ("x" * 1001, 6), ("q", 0), ("q", True)])
def test_invalid_requests(published, query, limit):
    retriever, first, _, _ = published
    with pytest.raises(RetrievalError, match="INVALID_QUERY"):
        retriever.search(str(first[0]), query, limit)


def test_missing_video_and_not_ready(published):
    retriever, first, _, _ = published
    with pytest.raises(RetrievalError, match="VIDEO_NOT_FOUND"):
        retriever.search(str(uuid4()), "Q")
    with pytest.raises(RetrievalError, match="INVALID_QUERY"):
        retriever.search("../../outside", "Q")
    retriever.repository.update_job(first[0], state=JobState.indexing, progress=90)
    with pytest.raises(RetrievalError, match="VIDEO_NOT_READY"):
        retriever.search(str(first[0]), "Q")


@pytest.mark.parametrize("filename", ["faiss.index", "bm25.pkl", "chunks.jsonl"])
def test_corrupted_artifact_rejected_before_deserialization(published, filename, monkeypatch):
    retriever, first, _, _ = published
    (first[2] / filename).write_bytes(b"corrupted")

    def forbidden(_):
        pytest.fail("pickle must not load a corrupt artifact")

    monkeypatch.setattr("listen_dragon.services.retrieval.pickle.load", forbidden)
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")


def test_manifest_model_and_version_mismatch(published):
    retriever, first, _, _ = published
    path = first[2] / "manifest.json"
    original = json.loads(path.read_text(encoding="utf-8"))
    for field, value, code in [
        ("embedding_model", "other-model", "EMBEDDING_MODEL_MISMATCH"),
        ("index_version", "a" * 16, "INDEX_VERSION_MISMATCH"),
    ]:
        path.write_text(json.dumps({**original, field: value}), encoding="utf-8")
        with pytest.raises(RetrievalError, match=code):
            retriever.search(str(first[0]), "Q")


def test_mixed_database_versions_fail_closed(published):
    retriever, first, _, _ = published
    with sqlite3.connect(retriever.repository.database_path) as connection:
        connection.execute("UPDATE document_chunk SET index_version = 'bad' WHERE id = 'first-1'")
    with pytest.raises(RetrievalError, match="INDEX_VERSION_MISMATCH"):
        retriever.search(str(first[0]), "Q")


def test_other_video_chunks_rejected_even_with_valid_hash(published):
    retriever, first, second, _ = published
    target = first[2] / "chunks.jsonl"
    target.write_bytes((second[2] / "chunks.jsonl").read_bytes())
    manifest_path = first[2] / "manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"]["chunks.jsonl"] = hashlib.sha256(target.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RetrievalError, match="INDEX_VERSION_MISMATCH"):
        retriever.search(str(first[0]), "Q")


def test_dimension_mismatch_and_no_keyword_match(published):
    retriever, first, _, dense = published
    report = retriever.search_detailed(str(first[0]), "zzzz-unseen", mode="hybrid")
    vector = retriever.search_detailed(str(first[0]), "zzzz-unseen", mode="vector")
    assert report.chunks == vector.chunks
    dense.d = 7
    with pytest.raises(RetrievalError, match="EMBEDDING_DIMENSION_MISMATCH"):
        retriever.search(str(first[0]), "Q")


@pytest.mark.parametrize("version,code", [("../outside", "INDEX_VERSION_MISMATCH"),
                                        ("f" * 16, "INDEX_NOT_FOUND")])
def test_invalid_or_missing_index_version(published, version, code):
    retriever, first, _, _ = published
    retriever.repository.set_chunk_index_version(first[0], version)
    with pytest.raises(RetrievalError, match=code):
        retriever.search(str(first[0]), "Q")


def test_nan_embedding_rejected(published):
    retriever, first, _, _ = published

    class BadEncoder:
        def encode(self, texts, **kwargs):
            return [[float("nan"), 0.0] for _ in texts]

    retriever._model_factory = lambda _: BadEncoder()
    with pytest.raises(RetrievalError, match="EMBEDDING_FAILED"):
        retriever.search(str(first[0]), "Q")


def test_invalid_faiss_position_rejected(published, monkeypatch):
    retriever, first, _, dense = published
    monkeypatch.setattr(dense, "search", lambda *_: (np.array([[1.0]]), np.array([[999]])))
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")


def test_cli_evaluation_does_not_send_cloud_queries_without_flag(published, tmp_path, monkeypatch):
    from listen_dragon import retrieve

    retriever, first, _, _ = published

    class ForbiddenExpander:
        def expand(self, _):
            pytest.fail("Cloud queries require explicit CLI flag")

    retriever.expander = ForbiddenExpander()
    fixture = tmp_path / "evaluation.json"
    fixture.write_text(json.dumps([{
        "id": "test", "source": "fixture", "query": "课题分离",
        "answer_start_ms": 1100, "answer_end_ms": 2400,
    }]), encoding="utf-8")
    output = tmp_path / "result.json"
    monkeypatch.setattr(retrieve, "build_retriever", lambda _: retriever)
    monkeypatch.setattr("sys.argv", ["retrieve", str(first[0]), "--evaluate", str(fixture),
                                     "--output", str(output)])
    assert retrieve.main() == 0
    metrics = json.loads(output.read_text(encoding="utf-8"))["metrics"]
    assert set(metrics) == {"vector", "hybrid"}
    assert metrics["hybrid"]["hit_at_1"] == 1.0


@pytest.mark.parametrize("field,value", [("chunk_count", 999), ("files", {})])
def test_corrupt_manifest_structure(published, field, value):
    retriever, first, _, _ = published
    path = first[2] / "manifest.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest[field] = value
    path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")


def test_malformed_manifest_json_and_missing_file(published):
    retriever, first, _, _ = published
    path = first[2] / "manifest.json"
    path.write_text("{bad-json", encoding="utf-8")
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")
    path.rename(first[2] / "manifest-moved.json")
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")


def test_empty_chunk_table(published):
    retriever, first, _, _ = published
    retriever.repository.replace_chunks(first[0], [])
    with pytest.raises(RetrievalError, match="INDEX_NOT_FOUND"):
        retriever.search(str(first[0]), "Q")


@pytest.mark.parametrize("scores", [[1.0], [float("nan")] * 3])
def test_corrupt_sparse_scores(published, monkeypatch, scores):
    retriever, first, _, _ = published
    monkeypatch.setattr(SparseIndex, "get_scores", lambda *_: scores)
    with pytest.raises(RetrievalError, match="INDEX_CORRUPT"):
        retriever.search(str(first[0]), "Q")


def test_search_exception_and_padding(published, monkeypatch):
    retriever, first, _, dense = published
    monkeypatch.setattr(dense, "search", lambda *_: (np.array([[1.0]]), np.array([[-1]])))
    assert retriever.search_detailed(str(first[0]), "Q", mode="vector").chunks == ()

    def broken(*_):
        raise RuntimeError("private path detail")

    monkeypatch.setattr(dense, "search", broken)
    with pytest.raises(RetrievalError, match="^RETRIEVAL_FAILED$"):
        retriever.search(str(first[0]), "Q")


def test_default_dependency_factories_and_settings(published, monkeypatch):
    from types import SimpleNamespace

    from listen_dragon.core.config import Settings
    from listen_dragon.services.retrieval import build_retriever

    retriever, first, _, dense = published
    monkeypatch.setitem(__import__("sys").modules, "faiss", SimpleNamespace(read_index=lambda _: dense))
    monkeypatch.setitem(__import__("sys").modules, "sentence_transformers",
                        SimpleNamespace(SentenceTransformer=lambda _: Encoder()))
    settings = Settings(
        _env_file=None, database_url=f"sqlite:///{retriever.repository.database_path}",
        data_root=str(retriever.data_root), embedding_model="test-model",
        query_expansion_enabled=False,
    )
    actual = build_retriever(settings)
    assert actual.search(str(first[0]), "课题分离")[0].chunk_id == "first-2"


def test_encoder_failure_and_bad_shape(published):
    retriever, first, _, _ = published

    def broken(_):
        raise RuntimeError("private path")

    retriever._model_factory = broken
    with pytest.raises(RetrievalError, match="^EMBEDDING_FAILED$"):
        retriever.search(str(first[0]), "Q")

    class WrongShape:
        def encode(self, *_args, **_kwargs):
            return [1.0, 0.0]

    retriever._model_factory = lambda _: WrongShape()
    with pytest.raises(RetrievalError, match="EMBEDDING_DIMENSION_MISMATCH"):
        retriever.search(str(first[0]), "Q")
