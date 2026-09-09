import hashlib
import json
import wave
from pathlib import Path
from uuid import uuid4

import pytest
from scripts.verify_video_artifacts import ArtifactValidationError, validate_video_artifacts


def write_valid_artifacts(data_root: Path, video_id: str) -> Path:
    artifact_dir = data_root / "artifacts" / video_id
    artifact_dir.mkdir(parents=True)
    with wave.open(str(artifact_dir / "audio.wav"), "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(16000)
        audio.writeframes(b"\x00\x00" * 160)
    (artifact_dir / "transcript.jsonl").write_text(
        json.dumps(
            {"start_ms": 0, "end_ms": 1000, "text": "这是中文转写。", "language": "zh"},
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    chunk = {
        "chunk_id": "chunk-1",
        "start_ms": 0,
        "end_ms": 1000,
        "text": "这是中文转写。",
        "token_count": 8,
    }
    (artifact_dir / "chunks.jsonl").write_text(
        json.dumps(chunk, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    version_dir = data_root / "indexes" / video_id / "test-version"
    version_dir.mkdir(parents=True)
    files = {
        "faiss.index": b"faiss-index",
        "bm25.pkl": b"bm25-index",
        "chunks.jsonl": (json.dumps(chunk, ensure_ascii=False) + "\n").encode(),
    }
    hashes = {}
    for filename, payload in files.items():
        (version_dir / filename).write_bytes(payload)
        hashes[filename] = hashlib.sha256(payload).hexdigest()
    (version_dir / "manifest.json").write_text(
        json.dumps(
            {
                "index_version": "test-version",
                "embedding_model": "test-model",
                "chunk_count": 1,
                "files": hashes,
            }
        ),
        encoding="utf-8",
    )
    return version_dir


def test_validator_accepts_complete_artifact_set(tmp_path: Path) -> None:
    video_id = str(uuid4())
    write_valid_artifacts(tmp_path, video_id)

    result = validate_video_artifacts(video_id, tmp_path)

    assert result["audio"]["channels"] == 1
    assert result["audio"]["sample_rate"] == 16000
    assert result["transcript_segments"] == 1
    assert result["chunks"] == 1
    assert result["indexes"][0]["index_version"] == "test-version"


def test_validator_rejects_tampered_index_file(tmp_path: Path) -> None:
    video_id = str(uuid4())
    version_dir = write_valid_artifacts(tmp_path, video_id)
    (version_dir / "faiss.index").write_bytes(b"tampered")

    with pytest.raises(ArtifactValidationError, match="SHA256 mismatch"):
        validate_video_artifacts(video_id, tmp_path)


def test_validator_rejects_invalid_audio_format(tmp_path: Path) -> None:
    video_id = str(uuid4())
    write_valid_artifacts(tmp_path, video_id)
    audio_path = tmp_path / "artifacts" / video_id / "audio.wav"
    with wave.open(str(audio_path), "wb") as audio:
        audio.setnchannels(2)
        audio.setsampwidth(2)
        audio.setframerate(44100)
        audio.writeframes(b"\x00\x00" * 160)

    with pytest.raises(ArtifactValidationError, match="mono WAV"):
        validate_video_artifacts(video_id, tmp_path)
