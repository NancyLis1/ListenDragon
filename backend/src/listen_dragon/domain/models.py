from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, Field


class JobState(StrEnum):
    queued = "QUEUED"
    extracting = "EXTRACTING"
    transcribing = "TRANSCRIBING"
    translating = "TRANSLATING"
    chunking = "CHUNKING"
    indexing = "INDEXING"
    ready = "READY"
    failed = "FAILED"


class VideoJobAccepted(BaseModel):
    video_id: UUID
    state: JobState


class VideoJobView(BaseModel):
    video_id: UUID
    state: JobState
    progress: int = Field(ge=0, le=100)
    error_code: str | None = None
