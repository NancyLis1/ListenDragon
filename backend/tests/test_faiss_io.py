import numpy as np
import pytest

from listen_dragon.infrastructure.faiss_io import read_index, write_index


def test_real_faiss_round_trip_in_unicode_directory(tmp_path):
    faiss = pytest.importorskip("faiss")
    path = tmp_path / "小学期 空格" / "检索索引.index"
    path.parent.mkdir()
    index = faiss.IndexFlatIP(2)
    index.add(np.array([[1, 0], [0, 1]], dtype="float32"))
    write_index(index, str(path))
    restored = read_index(str(path))
    scores, ids = restored.search(np.array([[0, 1]], dtype="float32"), 1)
    assert restored.ntotal == 2
    assert ids.tolist() == [[1]]
    assert scores.tolist() == [[1.0]]
