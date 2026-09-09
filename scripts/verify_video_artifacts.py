from __future__ import annotations

import argparse
import hashlib
import json
import wave
from pathlib import Path
from typing import Any
from uuid import UUID


class ArtifactValidationError(RuntimeError):
    """Raised when a completed video job has missing or inconsistent artifacts."""


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _read_jsonl(path: Path, required_fields: set[str]) -> list[dict[str, Any]]:
    if not path.is_file():
        raise ArtifactValidationError(f"Missing JSONL artifact: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArtifactValidationError(
                f"Invalid JSON at {path}:{line_number}: {exc.msg}"
            ) from exc
        missing = required_fields - set(row)
        if missing:
            raise ArtifactValidationError(
                f"Missing fields at {path}:{line_number}: {sorted(missing)}"
            )
        if not str(row["text"]).strip():
            raise ArtifactValidationError(f"Empty text at {path}:{line_number}")
        if int(row["start_ms"]) < 0 or int(row["end_ms"]) <= int(row["start_ms"]):
            raise ArtifactValidationError(f"Invalid timestamps at {path}:{line_number}")
        rows.append(row)
    if not rows:
        raise ArtifactValidationError(f"JSONL artifact contains no records: {path}")
    return rows


def _validate_audio(path: Path) -> dict[str, int]:
    if not path.is_file() or path.stat().st_size == 0:
        raise ArtifactValidationError(f"Missing or empty audio artifact: {path}")
    try:
        with wave.open(str(path), "rb") as audio:
            channels = audio.getnchannels()
            sample_rate = audio.getframerate()
            sample_width = audio.getsampwidth()
            frames = audio.getnframes()
    except (wave.Error, EOFError) as exc:
        raise ArtifactValidationError(f"Invalid WAV artifact: {path}") from exc
    if channels != 1:
        raise ArtifactValidationError(f"Expected mono WAV, got {channels} channels")
    if sample_rate != 16000:
        raise ArtifactValidationError(f"Expected 16000 Hz WAV, got {sample_rate} Hz")
    if sample_width != 2 or frames <= 0:
        raise ArtifactValidationError("Expected non-empty 16-bit PCM WAV")
    return {
        "channels": channels,
        "sample_rate": sample_rate,
        "sample_width_bytes": sample_width,
        "frames": frames,
    }


def _validate_index(version_dir: Path, expected_chunk_count: int) -> dict[str, Any]:
    manifest_path = version_dir / "manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ArtifactValidationError(f"Invalid index manifest: {manifest_path}") from exc
    if manifest.get("index_version") != version_dir.name:
        raise ArtifactValidationError("Manifest index_version does not match directory name")
    if manifest.get("chunk_count") != expected_chunk_count:
        raise ArtifactValidationError(
            f"Manifest chunk_count={manifest.get('chunk_count')} does not match "
            f"artifacts={expected_chunk_count}"
        )
    files = manifest.get("files")
    required_files = {"faiss.index", "bm25.pkl", "chunks.jsonl"}
    if not isinstance(files, dict) or set(files) != required_files:
        raise ArtifactValidationError("Manifest files must contain FAISS, BM25 and chunks JSONL")
    for filename, expected_hash in files.items():
        file_path = version_dir / filename
        if not file_path.is_file():
            raise ArtifactValidationError(f"Missing index artifact: {file_path}")
        actual_hash = _sha256(file_path)
        if actual_hash != expected_hash:
            raise ArtifactValidationError(
                f"SHA256 mismatch for {file_path}: expected {expected_hash}, got {actual_hash}"
            )
    return {
        "index_version": version_dir.name,
        "embedding_model": manifest.get("embedding_model"),
        "chunk_count": manifest["chunk_count"],
    }


def validate_video_artifacts(video_id: str | UUID, data_root: Path) -> dict[str, Any]:
    normalized_id = str(UUID(str(video_id)))
    artifact_dir = data_root / "artifacts" / normalized_id
    audio = _validate_audio(artifact_dir / "audio.wav")
    transcript = _read_jsonl(
        artifact_dir / "transcript.jsonl",
        {"start_ms", "end_ms", "text", "language"},
    )
    chunks = _read_jsonl(
        artifact_dir / "chunks.jsonl",
        {"chunk_id", "start_ms", "end_ms", "text", "token_count"},
    )

    index_root = data_root / "indexes" / normalized_id
    version_dirs = sorted(
        path for path in index_root.iterdir() if path.is_dir() and not path.name.startswith(".")
    ) if index_root.is_dir() else []
    if not version_dirs:
        raise ArtifactValidationError(f"No completed index version found: {index_root}")
    indexes = [_validate_index(path, len(chunks)) for path in version_dirs]
    return {
        "video_id": normalized_id,
        "audio": audio,
        "transcript_segments": len(transcript),
        "chunks": len(chunks),
        "indexes": indexes,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate ListenDragon video artifacts")
    parser.add_argument("video_id", help="Video UUID returned by the upload API")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    args = parser.parse_args()
    try:
        result = validate_video_artifacts(args.video_id, args.data_root.resolve())
    except (ArtifactValidationError, ValueError) as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False, indent=2))
        return 1
    print(json.dumps({"status": "PASSED", **result}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
