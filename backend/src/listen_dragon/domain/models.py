from datetime import datetime
from enum import StrEnum
from typing import Literal
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


class VideoView(VideoJobView):
    original_name: str
    mime: str
    size_bytes: int = Field(ge=0)
    duration_ms: int | None = Field(default=None, gt=0)
    created_at: datetime


class VideoListView(BaseModel):
    items: list[VideoView]


class TranscriptSegmentView(BaseModel):
    seq: int = Field(ge=0)
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str
    language: str


class TranscriptView(BaseModel):
    video_id: UUID
    segments: list[TranscriptSegmentView]


class SearchRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    query: str = Field(min_length=1, max_length=1000)
    video_ids: list[UUID] = Field(min_length=1, max_length=50)
    limit: int = Field(default=20, ge=1, le=50)


class SearchResultView(BaseModel):
    video_id: UUID
    original_name: str
    chunk_id: str
    start_ms: int = Field(ge=0)
    end_ms: int = Field(gt=0)
    text: str
    score: float


class SearchView(BaseModel):
    results: list[SearchResultView]


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


class ConversationMessageView(BaseModel):
    message_id: UUID
    role: Literal["user", "assistant"]
    content: str
    evidence: list[EvidenceView]
    created_at: datetime


class ConversationView(ConversationCreated):
    messages: list[ConversationMessageView]


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
