from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse

from listen_dragon.api.errors import mapped_api_error
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.domain.models import (
    JobState,
    TranscriptSegmentView,
    TranscriptView,
    UploadLimitsView,
    VideoJobAccepted,
    VideoListView,
    VideoView,
    VisualAnalysisView,
)
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url

router = APIRouter(prefix="/videos", tags=["videos"])

_UPLOAD_CHUNK_BYTES = 1024 * 1024
_ALLOWED_MEDIA_TYPES = {
    ".mkv": "video/x-matroska",
    ".mov": "video/quicktime",
    ".mp4": "video/mp4",
    ".webm": "video/webm",
}


def get_job_repository(
    settings: Annotated[Settings, Depends(get_settings)],
) -> SqliteJobRepository:
    repository = SqliteJobRepository(sqlite_path_from_url(settings.database_url))
    repository.initialize()
    return repository


@router.get("/upload-limits", response_model=UploadLimitsView)
def get_upload_limits(settings: Annotated[Settings, Depends(get_settings)]) -> UploadLimitsView:
    # Explicit public fields only; never serialize the application settings.
    return UploadLimitsView(
        max_upload_bytes=settings.max_upload_mb * 1024 * 1024,
        max_video_minutes=settings.max_video_minutes,
    )


@router.post("", response_model=VideoJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    file: Annotated[UploadFile, File()],
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoJobAccepted:
    suffix = Path(file.filename or "").suffix.lower()
    expected_media_type = _ALLOWED_MEDIA_TYPES.get(suffix)
    if expected_media_type is None or file.content_type != expected_media_type:
        raise mapped_api_error("UNSUPPORTED_MEDIA_TYPE")

    video_id = uuid4()
    video_dir = Path(settings.data_root) / "uploads" / str(video_id)
    temporary_path = video_dir / "source.uploading"
    source_path = video_dir / f"source{suffix}"
    size_bytes = 0
    digest = hashlib.sha256()
    max_upload_bytes = settings.max_upload_mb * 1024 * 1024

    try:
        video_dir.mkdir(parents=True, exist_ok=False)
        with temporary_path.open("xb") as destination:
            while chunk := await file.read(_UPLOAD_CHUNK_BYTES):
                size_bytes += len(chunk)
                if size_bytes > max_upload_bytes:
                    raise mapped_api_error("UPLOAD_TOO_LARGE")
                digest.update(chunk)
                destination.write(chunk)

        if size_bytes == 0:
            raise mapped_api_error("UPLOAD_EMPTY")

        temporary_path.replace(source_path)
        job = repository.create_video_job(
            video_id=video_id,
            original_name=Path(file.filename or "video").name,
            mime=expected_media_type,
            size_bytes=size_bytes,
            sha256=digest.hexdigest(),
            source_path=source_path,
        )
        return VideoJobAccepted(video_id=job.video_id, state=job.state)
    except Exception:
        temporary_path.unlink(missing_ok=True)
        source_path.unlink(missing_ok=True)
        if video_dir.exists():
            try:
                video_dir.rmdir()
            except OSError:
                pass
        raise
    finally:
        await file.close()


def _video_view(video) -> VideoView:
    return VideoView(
        video_id=video.video_id,
        original_name=video.original_name,
        mime=video.mime,
        size_bytes=video.size_bytes,
        duration_ms=video.duration_ms,
        created_at=video.created_at,
        state=video.state,
        progress=video.progress,
        error_code=video.error_code,
    )


@router.get("", response_model=VideoListView)
def list_videos(
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoListView:
    return VideoListView(items=[_video_view(item) for item in repository.list_videos()])


@router.get("/{video_id}", response_model=VideoView)
def get_video(
    video_id: UUID,
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoView:
    video = repository.get_stored_video(video_id)
    if video is None:
        raise mapped_api_error("VIDEO_NOT_FOUND")
    return _video_view(video)


@router.get("/{video_id}/transcript", response_model=TranscriptView)
def get_transcript(
    video_id: UUID,
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> TranscriptView:
    video = repository.get_stored_video(video_id)
    if video is None:
        raise mapped_api_error("VIDEO_NOT_FOUND")
    if video.state is not JobState.ready:
        raise mapped_api_error("VIDEO_NOT_READY")
    segments = repository.list_transcript_segments(video_id)
    return TranscriptView(
        video_id=video_id,
        segments=[
            TranscriptSegmentView(seq=seq, **segment.__dict__)
            for seq, segment in enumerate(segments)
        ],
    )


@router.get("/{video_id}/visual-analysis", response_model=VisualAnalysisView)
def get_visual_analysis(
    video_id: UUID,
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VisualAnalysisView:
    video = repository.get_stored_video(video_id)
    if video is None:
        raise mapped_api_error("VIDEO_NOT_FOUND")
    result = repository.get_visual_analysis(video_id)
    if video.state in {JobState.visualizing, JobState.chunking, JobState.indexing}:
        result.status = "pending"
    return result


@router.post("/{video_id}/visual-analysis", response_model=VideoJobAccepted, status_code=202)
def queue_visual_analysis(
    video_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoJobAccepted:
    video = repository.get_stored_video(video_id)
    if video is None:
        raise mapped_api_error("VIDEO_NOT_FOUND")
    if not settings.vision_enabled:
        raise mapped_api_error("VISION_DISABLED")
    if not all((settings.llm_base_url, settings.llm_api_key,
                settings.vision_model or settings.llm_model)):
        raise mapped_api_error("VISION_NOT_CONFIGURED")
    if not video.duration_ms or not repository.queue_visual_analysis(video_id):
        raise mapped_api_error("VIDEO_NOT_READY")
    return VideoJobAccepted(video_id=video_id, state=JobState.visualizing)


@router.get("/{video_id}/content", response_class=FileResponse)
def get_video_content(
    video_id: UUID,
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> FileResponse:
    video = repository.get_stored_video(video_id)
    if video is None:
        raise mapped_api_error("VIDEO_NOT_FOUND")
    uploads_root = (Path(settings.data_root) / "uploads").resolve()
    source_path = video.source_path
    source = source_path.resolve()
    if (
        not source.is_relative_to(uploads_root)
        or source_path.is_symlink()
        or not source.is_file()
    ):
        raise mapped_api_error("VIDEO_FILE_NOT_FOUND")
    return FileResponse(
        source,
        media_type=video.mime,
        filename=video.original_name,
        content_disposition_type="inline",
    )
