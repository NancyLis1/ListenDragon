import logging
import os
import socket
import time
from pathlib import Path

from listen_dragon.core.config import get_settings
from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.media import FfmpegMediaExtractor, MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url
from listen_dragon.services.contracts import MediaExtractor

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s component=worker %(message)s",
)
logger = logging.getLogger(__name__)


def process_next_job(
    *,
    repository: SqliteJobRepository,
    extractor: MediaExtractor,
    data_root: Path,
    worker_id: str,
    lease_seconds: int,
) -> bool:
    video = repository.claim_audio_extraction(
        worker_id=worker_id,
        lease_seconds=lease_seconds,
    )
    if video is None:
        return False

    audio_path = data_root / "artifacts" / str(video.video_id) / "audio.wav"
    logger.info("audio_extraction_started video_id=%s", video.video_id)
    try:
        extractor.extract_audio(video.source_path, audio_path)
        repository.update_job(video.video_id, state=JobState.transcribing, progress=30)
        logger.info("audio_extraction_finished video_id=%s", video.video_id)
    except MediaProcessingError as exc:
        repository.update_job(
            video.video_id,
            state=JobState.failed,
            progress=10,
            error_code=exc.error_code,
        )
        logger.warning(
            "audio_extraction_failed video_id=%s error_code=%s message=%s",
            video.video_id,
            exc.error_code,
            exc,
        )
    except Exception:
        repository.update_job(
            video.video_id,
            state=JobState.failed,
            progress=10,
            error_code="AUDIO_EXTRACTION_INTERNAL_ERROR",
        )
        logger.exception("audio_extraction_failed video_id=%s", video.video_id)
    return True


def run() -> None:
    settings = get_settings()
    repository = SqliteJobRepository(sqlite_path_from_url(settings.database_url))
    repository.initialize()
    extractor = FfmpegMediaExtractor(
        ffmpeg_binary=settings.ffmpeg_binary,
        ffprobe_binary=settings.ffprobe_binary,
        max_video_minutes=settings.max_video_minutes,
    )
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
            data_root=Path(settings.data_root),
            worker_id=worker_id,
            lease_seconds=settings.worker_lease_seconds,
        )
        if not worked:
            time.sleep(settings.worker_poll_seconds)


if __name__ == "__main__":
    run()
