from types import SimpleNamespace
from uuid import UUID, uuid4

import httpx
import pytest

from listen_dragon.api.dependencies import get_retriever
from listen_dragon.main import app
from listen_dragon.services.contracts import RetrievedChunk
from listen_dragon.services.retrieval import RetrievalError, SearchReport


class SearchRepository:
    def __init__(self, video_id: UUID) -> None:
        self.video_id = video_id

    def list_videos(self):
        return [SimpleNamespace(video_id=self.video_id, original_name="lesson.mp4")]


class SearchRetriever:
    def __init__(self, video_id: UUID) -> None:
        self.video_id = video_id
        self.repository = SearchRepository(video_id)
        self.calls = []

    def search_many(self, video_ids, query, *, limit_per_video):
        self.calls.append((video_ids, query, limit_per_video))
        return (SearchReport(
            str(self.video_id), "a" * 16, (query,),
            (RetrievedChunk("chunk-1", 1000, 2500, "检索结果", 0.1),), None, 1.0,
        ),)


@pytest.mark.asyncio
async def test_search_api_returns_timestamped_cross_video_results() -> None:
    video_id = uuid4()
    retriever = SearchRetriever(video_id)
    app.dependency_overrides[get_retriever] = lambda: retriever
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/search", json={
                "query": "讲了什么？", "video_ids": [str(video_id)], "limit": 20,
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["results"][0] == {
        "video_id": str(video_id), "original_name": "lesson.mp4", "chunk_id": "chunk-1",
        "start_ms": 1000, "end_ms": 2500, "text": "检索结果", "score": 0.1,
    }
    assert retriever.calls == [([str(video_id)], "讲了什么？", 6)]


@pytest.mark.asyncio
async def test_search_api_maps_retrieval_failures() -> None:
    class BrokenRetriever(SearchRetriever):
        def search_many(self, *args, **kwargs):
            raise RetrievalError("VIDEO_NOT_READY")

    video_id = uuid4()
    app.dependency_overrides[get_retriever] = lambda: BrokenRetriever(video_id)
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.post("/api/v1/search", json={
                "query": "Q", "video_ids": [str(video_id)],
            })
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 409
    assert response.json()["error_code"] == "VIDEO_NOT_READY"
