from pathlib import Path
from uuid import uuid4

import pytest

from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.contracts import DocumentChunk, TranscriptSegment


def create_repository(tmp_path: Path) -> SqliteJobRepository:
    repository = SqliteJobRepository(tmp_path / "jobs.db")
    repository.initialize()
    return repository


def create_job(repository: SqliteJobRepository, tmp_path: Path):
    video_id = uuid4()
    source = tmp_path / "uploads" / str(video_id) / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    repository.create_video_job(
        video_id=video_id,
        original_name="中文课程.mp4",
        mime="video/mp4",
        size_bytes=source.stat().st_size,
        sha256="sha256",
        source_path=source,
    )
    return video_id


def test_job_claim_is_exclusive_while_lease_is_active(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)
    video_id = create_job(repository, tmp_path)

    first = repository.claim_audio_extraction(worker_id="worker-a", lease_seconds=60)
    second = repository.claim_audio_extraction(worker_id="worker-b", lease_seconds=60)

    assert first is not None and first.video_id == video_id
    assert second is None
    assert repository.get_video_job(video_id).state is JobState.extracting


def test_transcript_and_chunks_can_be_replaced_without_duplicates(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)
    video_id = create_job(repository, tmp_path)
    segments = [TranscriptSegment(0, 1000, "第一段中文内容", "zh")]
    chunks = [DocumentChunk("chunk-1", 0, 1000, "第一段中文内容", 8)]

    repository.replace_transcript_segments(video_id, segments)
    repository.replace_transcript_segments(video_id, segments)
    repository.replace_chunks(video_id, chunks)
    repository.replace_chunks(video_id, chunks)

    assert repository.list_transcript_segments(video_id) == segments
    assert repository.list_chunks(video_id) == chunks


def test_updating_unknown_job_raises_key_error(tmp_path: Path) -> None:
    repository = create_repository(tmp_path)

    with pytest.raises(KeyError, match="Unknown video job"):
        repository.update_job(uuid4(), state=JobState.failed, progress=10, error_code="TEST")
