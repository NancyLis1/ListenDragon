from pathlib import Path
from uuid import UUID, uuid4

import pytest

from listen_dragon.domain.models import JobState, VisualObservation
from listen_dragon.infrastructure.asr import TranscriptionError
from listen_dragon.infrastructure.media import MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.services.chunking import SemanticChunker
from listen_dragon.services.contracts import DocumentChunk, ExtractedMedia, TranscriptSegment
from listen_dragon.services.llm_generation import GenerationError
from listen_dragon.worker import process_next_job


class SuccessfulExtractor:
    def extract_audio(self, video: Path, output: Path) -> ExtractedMedia:
        assert video.read_bytes() == b"video"
        output.parent.mkdir(parents=True)
        output.write_bytes(b"wav")
        return ExtractedMedia(output, 12_500)


class FailingExtractor:
    def extract_audio(self, video: Path, output: Path) -> ExtractedMedia:
        raise MediaProcessingError("INVALID_MEDIA", "not a real video")


class VisualAnalyzer:
    def analyze(self, video, duration_ms, output):
        return [VisualObservation(timestamp_ms=1000, text="桌上可见打开的西瓜。")]


@pytest.mark.parametrize("audio_mode", ["speech", "empty", "no_audio_track"])
def test_visual_pipeline_preserves_speech_and_supports_silent_video(tmp_path, audio_mode):
    repository, data_root, video_id = create_job(tmp_path)
    dependencies = worker_dependencies()
    extractor = SuccessfulExtractor()
    if audio_mode == "empty":
        class EmptyRecognizer:
            def transcribe(self, audio):
                raise TranscriptionError("ASR_EMPTY", "empty")
        dependencies["recognizer"] = EmptyRecognizer()
    if audio_mode == "no_audio_track":
        class NoAudioExtractor:
            def extract_audio(self, video, output):
                raise MediaProcessingError("FFMPEG_FAILED", "no audio", 12500)
        extractor = NoAudioExtractor()
    for _ in range(5):
        process_next_job(repository=repository, extractor=extractor, **dependencies,
                         visual_analyzer=VisualAnalyzer(), data_root=data_root,
                         worker_id="test", lease_seconds=60)
    assert repository.get_video_job(video_id).state is JobState.ready
    analysis = repository.get_visual_analysis(video_id)
    assert analysis.status == "ready"
    assert bool(analysis.audio_warning) == (audio_mode != "speech")
    assert any(c.chunk_id.startswith("visual:") for c in repository.list_chunks(video_id))
    transcript = repository.list_transcript_segments(video_id)
    assert bool(transcript) == (audio_mode == "speech")
    assert all("西瓜" not in item.text for item in transcript)


def test_visual_failure_is_explicit_and_retains_usable_speech(tmp_path):
    repository, data_root, video_id = create_job(tmp_path)
    class FailingVision:
        def analyze(self, *args):
            raise GenerationError("LLM_UNAVAILABLE")
    for _ in range(5):
        process_next_job(repository=repository, extractor=SuccessfulExtractor(),
                         **worker_dependencies(), visual_analyzer=FailingVision(),
                         data_root=data_root, worker_id="test", lease_seconds=60)
    assert repository.get_video_job(video_id).state is JobState.ready
    assert repository.get_visual_analysis(video_id).error_code == "LLM_UNAVAILABLE"
    assert not any(c.chunk_id.startswith("visual:") for c in repository.list_chunks(video_id))


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


def test_targeted_worker_cannot_claim_another_video(tmp_path):
    repository, data_root, video_id = create_job(tmp_path)
    assert not process_next_job(repository=repository, extractor=SuccessfulExtractor(),
                                **worker_dependencies(), visual_analyzer=VisualAnalyzer(),
                                data_root=data_root, worker_id="test", lease_seconds=60,
                                target_video_id=uuid4())
    assert repository.get_video_job(video_id).state is JobState.queued
    for stage in (JobState.visualizing, JobState.chunking, JobState.indexing):
        repository.update_job(video_id, state=stage, progress=45)
        assert repository.claim_stage(stage, worker_id="test", lease_seconds=60,
                                      target_video_id=uuid4()) is None


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
    assert repository.get_stored_video(video_id).duration_ms == 12_500


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
