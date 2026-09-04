from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status

from listen_dragon.core.config import Settings, get_settings
from listen_dragon.domain.models import VideoJobAccepted, VideoJobView
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


@router.post("", response_model=VideoJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_video(
    file: Annotated[UploadFile, File()],
    settings: Annotated[Settings, Depends(get_settings)],
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoJobAccepted:
    suffix = Path(file.filename or "").suffix.lower()
    expected_media_type = _ALLOWED_MEDIA_TYPES.get(suffix)
    if expected_media_type is None or file.content_type != expected_media_type:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Unsupported video extension or media type",
        )

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
                    raise HTTPException(
                        status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                        detail=f"Video exceeds the {settings.max_upload_mb} MB upload limit",
                    )
                digest.update(chunk)
                destination.write(chunk)

        if size_bytes == 0:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Uploaded video is empty",
            )

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


@router.get("/{video_id}", response_model=VideoJobView)
def get_video(
    video_id: UUID,
    repository: Annotated[SqliteJobRepository, Depends(get_job_repository)],
) -> VideoJobView:
    job = repository.get_video_job(video_id)
    if job is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Video not found")
    return job
