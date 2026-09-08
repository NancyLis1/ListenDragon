"""Use Python path handling: FAISS native file I/O rejects Unicode paths on Windows."""
from pathlib import Path
from typing import Any


def write_index(index: Any, path: str) -> None:
    import faiss

    Path(path).write_bytes(faiss.serialize_index(index).tobytes())


def read_index(path: str) -> Any:
    import faiss
    import numpy as np

    return faiss.deserialize_index(np.frombuffer(Path(path).read_bytes(), dtype="uint8"))
