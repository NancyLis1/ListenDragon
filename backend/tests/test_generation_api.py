from pathlib import Path
from uuid import uuid4

import httpx
import pytest

from listen_dragon.api.generation import get_generation_service
from listen_dragon.domain.models import JobState
from listen_dragon.infrastructure.sqlite_conversations import SqliteConversationRepository
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.main import app
from listen_dragon.services.contracts import DocumentChunk, RetrievedChunk
from listen_dragon.services.grounded_generation import GroundedGenerationService
from listen_dragon.services.llm_generation import (
    AnswerDraft,
    GroundedClaim,
    SummaryDraft,
    SummarySection,
)


class Retriever:
    def search(self, video_id, query, limit=6):
        return [RetrievedChunk("chunk-1", 125000, 130000, "视频证据", 0.1)]


class Generator:
    def answer(self, *, question, conversation_summary, evidence):
        return AnswerDraft(True, (GroundedClaim("这是回答。", ("chunk-1",)),), "对话摘要")

    def summarize(self, *, evidence, language, length, format):
        return SummaryDraft("标题", (SummarySection("主题", "摘要内容", ("chunk-1",)),))

    def verify(self, *, question, claims, evidence):
        return (True,) * len(claims)

    def synthesize(self, **kwargs):
        raise AssertionError("single chunk should not synthesize")


@pytest.fixture
def api_context(tmp_path: Path):
    database = tmp_path / "api.db"
    jobs = SqliteJobRepository(database)
    jobs.initialize()
    conversations = SqliteConversationRepository(database)
    conversations.initialize()
    video_id = uuid4()
    source = tmp_path / "source.mp4"
    source.write_bytes(b"video")
    jobs.create_video_job(
        video_id=video_id,
        original_name="source.mp4",
        mime="video/mp4",
        size_bytes=5,
        sha256="0" * 64,
        source_path=source,
    )
    jobs.replace_chunks(video_id, [DocumentChunk("chunk-1", 125000, 130000, "视频证据", 4)])
    jobs.set_chunk_index_version(video_id, "b" * 16)
    jobs.update_job(video_id, state=JobState.ready, progress=100)
    service = GroundedGenerationService(jobs, conversations, Retriever(), Generator())
    app.dependency_overrides[get_generation_service] = lambda: service
    yield video_id
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_conversation_qa_and_summary_api_contract(api_context):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        created = await client.post("/api/v1/conversations", json={"video_id": str(api_context)})
        answer = await client.post(
            f"/api/v1/conversations/{created.json()['conversation_id']}/messages",
            json={"question": "视频讲了什么？"},
            headers={"X-Request-ID": "qa-test-1"},
        )
        summary = await client.post(
            f"/api/v1/videos/{api_context}/summary",
            json={"language": "zh-CN", "length": "medium", "format": "outline"},
        )
    assert created.status_code == 201
    assert answer.status_code == 200
    assert answer.headers["X-Request-ID"] == "qa-test-1"
    assert answer.json()["evidence"][0]["timestamp"] == "[02:05-02:10]"
    assert summary.status_code == 200
    assert summary.json()["cached"] is False
    assert summary.json()["evidence"][0]["video_id"] == str(api_context)


@pytest.mark.asyncio
async def test_generation_api_validation_and_not_found_error_are_structured(api_context):
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        invalid = await client.post("/api/v1/conversations", json={"video_id": "bad"})
        missing = await client.post(
            f"/api/v1/conversations/{uuid4()}/messages", json={"question": "Q"}
        )
    assert invalid.status_code == 422
    assert invalid.json()["error_code"] == "INVALID_REQUEST"
    assert invalid.json()["request_id"]
    assert missing.status_code == 404
    assert missing.json()["error_code"] == "CONVERSATION_NOT_FOUND"
    assert missing.json()["retryable"] is False
