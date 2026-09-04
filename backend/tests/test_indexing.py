import json
from pathlib import Path

from listen_dragon.infrastructure.indexing import HybridIndexBuilder, tokenize_for_bm25
from listen_dragon.services.contracts import DocumentChunk


class FakeEmbeddingModel:
    def encode(self, texts, **options):
        assert options["normalize_embeddings"] is True
        return [[float(len(text)), 1.0] for text in texts]


class FakeFaissIndex:
    def __init__(self, dimension: int) -> None:
        self.dimension = dimension
        self.embeddings = None

    def add(self, embeddings) -> None:
        self.embeddings = embeddings


def test_hybrid_index_builder_publishes_complete_version(tmp_path: Path) -> None:
    written_indexes = []

    def write_index(index: FakeFaissIndex, path: str) -> None:
        assert index.dimension == 2
        assert index.embeddings
        Path(path).write_bytes(b"faiss")
        written_indexes.append(path)

    builder = HybridIndexBuilder(
        embedding_model="test-model",
        model_factory=lambda _name: FakeEmbeddingModel(),
        array_factory=lambda values: values,
        index_factory=FakeFaissIndex,
        index_writer=write_index,
        bm25_factory=lambda tokens: {"tokens": tokens},
    )
    chunks = [
        DocumentChunk("chunk-1", 0, 1000, "介绍 Python 3.12", 4),
        DocumentChunk("chunk-2", 1000, 2000, "讲解向量检索", 6),
    ]

    result = builder.build(chunks, tmp_path / "indexes")

    manifest = json.loads((result / "manifest.json").read_text(encoding="utf-8"))
    assert written_indexes
    assert manifest["embedding_model"] == "test-model"
    assert manifest["chunk_count"] == 2
    assert set(manifest["files"]) == {"faiss.index", "bm25.pkl", "chunks.jsonl"}
    assert all((result / filename).is_file() for filename in manifest["files"])

    assert builder.build(chunks, tmp_path / "indexes") == result
    assert len(written_indexes) == 1


def test_bm25_tokenizer_keeps_terms_numbers_and_chinese_characters() -> None:
    assert tokenize_for_bm25("Python 3.12 与 FAISS检索") == [
        "python",
        "3",
        "12",
        "与",
        "faiss",
        "检",
        "索",
    ]
