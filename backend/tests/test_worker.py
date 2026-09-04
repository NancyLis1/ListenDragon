from pathlib import Path
from uuid import UUID, uuid4

from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.media import MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.worker import process_next_job


class SuccessfulExtractor:
    def extract_audio(self, video: Path, output: Path) -> Path:
        assert video.read_bytes() == b"video"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"wav")
        return output


class FailingExtractor:
    def extract_audio(self, video: Path, output: Path) -> Path:
        raise MediaProcessingError("INVALID_MEDIA", "not a real video")


def create_job(tmp_path: Path) -> tuple[SqliteJobRepository, Path, UUID]:
    data_root = tmp_path / "data"
    source = data_root / "uploads" / "source.mp4"
    source.parent.mkdir(parents=True)
    source.write_bytes(b"video")
    repository = SqliteJobRepository(data_root / "listendragon.db")
    repository.initialize()
    video_id = uuid4()
    repository.create_video_job(
        video_id=video_id,
        original_name="lesson.mp4",
        mime="video/mp4",
        size_bytes=source.stat().st_size,
        sha256="test-sha",
        source_path=source,
    )
    return repository, data_root, video_id


def test_worker_extracts_audio_and_advances_job(tmp_path: Path) -> None:
    repository, data_root, video_id = create_job(tmp_path)

    worked = process_next_job(
        repository=repository,
        extractor=SuccessfulExtractor(),
        data_root=data_root,
        worker_id="test-worker",
        lease_seconds=60,
    )

    assert worked is True
    assert (data_root / "artifacts" / str(video_id) / "audio.wav").read_bytes() == b"wav"
    job = repository.get_video_job(video_id)
    assert job is not None
    assert job.state is JobState.transcribing
    assert job.progress == 30


def test_worker_records_media_failure(tmp_path: Path) -> None:
    repository, data_root, video_id = create_job(tmp_path)

    worked = process_next_job(
        repository=repository,
        extractor=FailingExtractor(),
        data_root=data_root,
        worker_id="test-worker",
        lease_seconds=60,
    )

    assert worked is True
    job = repository.get_video_job(video_id)
    assert job is not None
    assert job.state is JobState.failed
    assert job.error_code == "INVALID_MEDIA"


def test_worker_returns_false_when_queue_is_empty(tmp_path: Path) -> None:
    repository = SqliteJobRepository(tmp_path / "listendragon.db")
    repository.initialize()

    worked = process_next_job(
        repository=repository,
        extractor=SuccessfulExtractor(),
        data_root=tmp_path,
        worker_id="test-worker",
        lease_seconds=60,
    )

    assert worked is False
