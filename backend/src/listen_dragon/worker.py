import json
import logging
import os
import socket
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import UUID

from listen_dragon.core.config import get_settings
from listen_dragon.domain.models import JobState, VisualAnalysisView
from listen_dragon.infrastructure.asr import FasterWhisperRecognizer, TranscriptionError
from listen_dragon.infrastructure.indexing import HybridIndexBuilder, IndexBuildError
from listen_dragon.infrastructure.media import FfmpegMediaExtractor, MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url
from listen_dragon.infrastructure.vision import FrameAnalyzer
from listen_dragon.services.chunking import SemanticChunker
from listen_dragon.services.contracts import (
    DocumentChunk,
    IndexBuilder,
    MediaExtractor,
    SpeechRecognizer,
    TextChunker,
)
from listen_dragon.services.llm_generation import GenerationError, OpenAITextGenerator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s component=worker %(message)s",
)
logger = logging.getLogger(__name__)


def process_next_job(
    *,
    repository: SqliteJobRepository,
    extractor: MediaExtractor,
    recognizer: SpeechRecognizer,
    chunker: TextChunker,
    index_builder: IndexBuilder,
    data_root: Path,
    worker_id: str,
    lease_seconds: int,
    visual_analyzer: FrameAnalyzer | None = None,
    target_video_id: UUID | None = None,
) -> bool:
    video = repository.claim_stage(
        JobState.indexing,
        target_video_id=target_video_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if video is not None:
        chunks = repository.list_chunks(video.video_id)
        try:
            index_path = index_builder.build(chunks, data_root / "indexes" / str(video.video_id))
            repository.set_chunk_index_version(video.video_id, index_path.name)
            repository.update_job(video.video_id, state=JobState.ready, progress=100)
            logger.info("index_build_finished video_id=%s", video.video_id)
        except IndexBuildError as exc:
            _fail_job(repository, video.video_id, 70, exc.error_code, exc)
        return True

    video = repository.claim_stage(
        JobState.chunking,
        target_video_id=target_video_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if video is not None:
        try:
            segments = repository.list_transcript_segments(video.video_id)
            chunks = list(chunker.split(str(video.video_id), segments))
            visual = repository.get_visual_analysis(video.video_id)
            for seq, observation in enumerate(visual.observations):
                text = "视频事件：" + observation.text
                chunks.append(DocumentChunk(
                    chunk_id=f"visual:{video.video_id}:{observation.timestamp_ms}:{seq}",
                    start_ms=observation.timestamp_ms,
                    end_ms=min(video.duration_ms, observation.end_ms or observation.timestamp_ms + 1000),
                    text=text, token_count=len(text),
                ))
            if not chunks:
                raise ValueError("Chunking produced no document chunks")
            repository.replace_chunks(video.video_id, chunks)
            _write_jsonl(
                data_root / "artifacts" / str(video.video_id) / "chunks.jsonl",
                [chunk.__dict__ for chunk in chunks],
            )
            repository.update_job(video.video_id, state=JobState.indexing, progress=70)
            logger.info("chunking_finished video_id=%s chunks=%s", video.video_id, len(chunks))
        except (OSError, ValueError) as exc:
            _fail_job(repository, video.video_id, 55, "CHUNKING_FAILED", exc)
        return True

    video = repository.claim_stage(
        JobState.visualizing, worker_id=worker_id, lease_seconds=lease_seconds,
        target_video_id=target_video_id,
    )
    if video is not None:
        prior = repository.get_visual_analysis(video.video_id)
        try:
            if visual_analyzer is None:
                raise GenerationError("VISION_DISABLED")
            observations = visual_analyzer.analyze(
                video.source_path, video.duration_ms,
                data_root / "artifacts" / str(video.video_id) / "frames",
            )
            repository.save_visual_analysis(video.video_id, VisualAnalysisView(
                status="ready", observations=observations, audio_warning=prior.audio_warning,
                version=getattr(visual_analyzer, "version", "frames-v1"),
                analyzed_at=datetime.now(UTC),
                sampling_note="已按连续片段分析事件；概括读取全片画面，细节问题会回看相关片段。抽样仍可能遗漏瞬间动作。",
            ))
            logger.info("visual_analysis_finished video_id=%s events=%s",
                        video.video_id, len(observations))
        except GenerationError as exc:
            repository.save_visual_analysis(video.video_id, VisualAnalysisView(
                status="failed", error_code=exc.error_code, audio_warning=prior.audio_warning,
            ))
            logger.warning("visual_analysis_failed video_id=%s error_code=%s",
                           video.video_id, exc.error_code)
            if not repository.list_transcript_segments(video.video_id):
                _fail_job(repository, video.video_id, 45, exc.error_code, exc)
                return True
        repository.update_job(video.video_id, state=JobState.chunking, progress=55)
        return True

    video = repository.claim_stage(
        JobState.transcribing,
        target_video_id=target_video_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if video is not None:
        audio_path = data_root / "artifacts" / str(video.video_id) / "audio.wav"
        try:
            segments = list(recognizer.transcribe(audio_path))
            if not segments and visual_analyzer is not None:
                repository.save_visual_analysis(video.video_id, VisualAnalysisView(
                    status="pending", audio_warning="NO_SPEECH",
                ))
            repository.replace_transcript_segments(video.video_id, segments)
            _write_jsonl(
                data_root / "artifacts" / str(video.video_id) / "transcript.jsonl",
                [segment.__dict__ for segment in segments],
            )
            repository.update_job(
                video.video_id,
                state=JobState.visualizing if visual_analyzer else JobState.chunking,
                progress=45 if visual_analyzer else 55,
            )
            logger.info(
                "transcription_finished video_id=%s segments=%s",
                video.video_id,
                len(segments),
            )
        except TranscriptionError as exc:
            if visual_analyzer is not None:
                repository.save_visual_analysis(video.video_id, VisualAnalysisView(
                    status="pending", audio_warning=exc.error_code,
                ))
                repository.update_job(video.video_id, state=JobState.visualizing, progress=45)
            else:
                _fail_job(repository, video.video_id, 30, exc.error_code, exc)
        return True

    video = repository.claim_audio_extraction(
        target_video_id=target_video_id,
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if video is None:
        return False

    audio_path = data_root / "artifacts" / str(video.video_id) / "audio.wav"
    logger.info("audio_extraction_started video_id=%s", video.video_id)
    try:
        extracted = extractor.extract_audio(video.source_path, audio_path)
        repository.set_video_duration(video.video_id, extracted.duration_ms)
        repository.update_job(video.video_id, state=JobState.transcribing, progress=30)
        logger.info("audio_extraction_finished video_id=%s", video.video_id)
    except MediaProcessingError as exc:
        if visual_analyzer is not None and exc.duration_ms:
            repository.set_video_duration(video.video_id, exc.duration_ms)
            repository.save_visual_analysis(video.video_id, VisualAnalysisView(
                status="pending", audio_warning=exc.error_code,
            ))
            repository.update_job(video.video_id, state=JobState.visualizing, progress=45)
        else:
            _fail_job(repository, video.video_id, 10, exc.error_code, exc)
    return True


def _write_jsonl(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".writing")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        for row in rows:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
    temporary.replace(path)


def _fail_job(
    repository: SqliteJobRepository,
    video_id: UUID,
    progress: int,
    error_code: str,
    error: Exception,
) -> None:
    repository.update_job(
        video_id,
        state=JobState.failed,
        progress=progress,
        error_code=error_code,
    )
    logger.warning(
        "job_failed video_id=%s error_code=%s message=%s",
        video_id,
        error_code,
        error,
    )


def run() -> None:
    settings = get_settings()
    repository = SqliteJobRepository(sqlite_path_from_url(settings.database_url))
    repository.initialize()
    extractor = FfmpegMediaExtractor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        max_video_minutes=settings.max_video_minutes,
    )
    recognizer = FasterWhisperRecognizer(
        model_name=settings.asr_model,
        device=settings.asr_device,
        compute_type=settings.asr_compute_type,
    )
    chunker = SemanticChunker(
        min_chars=settings.chunk_min_chars,
        target_chars=settings.chunk_target_chars,
        max_chars=settings.chunk_max_chars,
        overlap_chars=settings.chunk_overlap_chars,
    )
    index_builder = HybridIndexBuilder(embedding_model=settings.embedding_model)
    visual_analyzer = FrameAnalyzer(
        OpenAITextGenerator(
            base_url=settings.llm_base_url, api_key=settings.llm_api_key,
            model=settings.vision_model or settings.llm_model,
            timeout_seconds=max(60, settings.llm_timeout_seconds),
        ), ffmpeg_binary=settings.ffmpeg_binary,
        interval_seconds=settings.vision_interval_seconds, max_frames=settings.vision_max_frames,
        window_seconds=settings.vision_window_seconds,
        scene_detection=settings.vision_scene_detection, max_windows=settings.vision_max_windows,
    ) if settings.vision_enabled else None
    worker_id = f"{socket.gethostname()}:{os.getpid()}"
    logger.info(
        "worker_started worker_id=%s poll_seconds=%s concurrency=%s",
        worker_id,
        settings.worker_poll_seconds,
        settings.worker_concurrency,
    )
    while True:
        worked = process_next_job(
            repository=repository,
            extractor=extractor,
            recognizer=recognizer,
            chunker=chunker,
            index_builder=index_builder,
            data_root=Path(settings.data_root),
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
            visual_analyzer=visual_analyzer,
            target_video_id=UUID(settings.worker_video_id) if settings.worker_video_id else None,
        )
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
