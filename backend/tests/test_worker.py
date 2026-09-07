from pathlib import Path
from uuid import UUID, uuid4

from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.media import MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.chunking import SemanticChunker
from listen_dragon.services.contracts import DocumentChunk, TranscriptSegment
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


class SuccessfulRecognizer:
    def transcribe(self, audio: Path) -> list[TranscriptSegment]:
        assert audio.read_bytes() == b"wav"
        return [
            TranscriptSegment(0, 1000, "第一段课程内容", "zh"),
            TranscriptSegment(1000, 2000, "第二段课程内容", "zh"),
            TranscriptSegment(2000, 3000, "第三段课程内容", "zh"),
        ]


class SuccessfulIndexBuilder:
    def build(self, chunks: list[DocumentChunk], output_root: Path) -> Path:
        assert chunks
        target = output_root / "test-version"
        target.mkdir(parents=True)
        (target / "manifest.json").write_text("{}", encoding="utf-8")
        return target


def worker_dependencies() -> dict:
    return {
        "recognizer": SuccessfulRecognizer(),
        "chunker": SemanticChunker(
            min_chars=8,
            target_chars=12,
            max_chars=20,
            overlap_chars=2,
        ),
        "index_builder": SuccessfulIndexBuilder(),
    }


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
        **worker_dependencies(),
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


def test_worker_completes_transcription_chunking_and_indexing(tmp_path: Path) -> None:
    repository, data_root, video_id = create_job(tmp_path)
    dependencies = worker_dependencies()

    for _ in range(4):
        assert process_next_job(
            repository=repository,
            extractor=SuccessfulExtractor(),
            **dependencies,
            data_root=data_root,
            worker_id="test-worker",
            lease_seconds=60,
        )

    job = repository.get_video_job(video_id)
    assert job is not None
    assert job.state is JobState.ready
    assert job.progress == 100
    assert repository.list_transcript_segments(video_id)
    assert repository.list_chunks(video_id)
    assert (data_root / "artifacts" / str(video_id) / "transcript.jsonl").is_file()
    assert (data_root / "artifacts" / str(video_id) / "chunks.jsonl").is_file()
    assert (data_root / "indexes" / str(video_id) / "test-version" / "manifest.json").is_file()


def test_worker_records_media_failure(tmp_path: Path) -> None:
    repository, data_root, video_id = create_job(tmp_path)

    worked = process_next_job(
        repository=repository,
        extractor=FailingExtractor(),
        **worker_dependencies(),
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
        **worker_dependencies(),
        data_root=tmp_path,
        worker_id="test-worker",
        lease_seconds=60,
    )

    assert worked is False
