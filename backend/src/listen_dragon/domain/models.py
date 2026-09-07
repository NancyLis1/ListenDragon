from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


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


class SummaryLanguage(StrEnum):
    auto = "auto"
    chinese = "zh-CN"
    english = "en"


class SummaryLength(StrEnum):
    short = "short"
    medium = "medium"
    detailed = "detailed"


class SummaryFormat(StrEnum):
    outline = "outline"
    paragraphs = "paragraphs"


class SummaryRequest(BaseModel):
    language: SummaryLanguage = SummaryLanguage.auto
    length: SummaryLength = SummaryLength.medium
    format: SummaryFormat = SummaryFormat.outline


class EvidenceView(BaseModel):
    chunk_id: str = Field(min_length=1, max_length=200)
    video_id: UUID
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    timestamp: str = Field(pattern=r"^\[\d{2}(?::\d{2}){1,2}-\d{2}(?::\d{2}){1,2}\]$")
    text: str = Field(min_length=1)

    @model_validator(mode="after")
    def validate_time_range(self) -> "EvidenceView":
        if self.end_ms <= self.start_ms:
            raise ValueError("Evidence end_ms must be greater than start_ms")
        return self


class SummaryView(BaseModel):
    video_id: UUID
    summary: str
    evidence: list[EvidenceView]
    language: SummaryLanguage
    length: SummaryLength
    format: SummaryFormat
    cached: bool
    generated_at: datetime


class ConversationCreate(BaseModel):
    video_id: UUID


class ConversationCreated(BaseModel):
    conversation_id: UUID
    video_id: UUID
    created_at: datetime


class MessageCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    question: str = Field(min_length=1, max_length=1000)


class AnswerView(BaseModel):
    conversation_id: UUID
    message_id: UUID
    answer: str
    refused: bool
    evidence: list[EvidenceView]
    created_at: datetime


class ApiErrorView(BaseModel):
    error_code: str
    message: str
    request_id: str
    retryable: bool
    details: list[dict[str, object]] | None = None
