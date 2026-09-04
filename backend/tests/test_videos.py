import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from listen_dragon.api.videos import get_job_repository
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.main import app


@pytest.fixture
def upload_context(tmp_path: Path):
    data_root = tmp_path / "data"
    settings = Settings(
        data_root=str(data_root),
        database_url=f"sqlite:///{(data_root / 'listendragon.db').as_posix()}",
        max_upload_mb=1,
    )
    repository = SqliteJobRepository(data_root / "listendragon.db")
    repository.initialize()
    app.dependency_overrides[get_settings] = lambda: settings
    app.dependency_overrides[get_job_repository] = lambda: repository
    yield settings, repository
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_persists_file_and_job(upload_context) -> None:
    settings, repository = upload_context
    payload = b"small-test-video"
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("lesson.mp4", payload, "video/mp4")},
        )

    assert response.status_code == 202
    body = response.json()
    assert body["state"] == "QUEUED"

    stored = repository.get_stored_video(UUID(body["video_id"]))
    assert stored is not None
    assert stored.original_name == "lesson.mp4"
    assert stored.size_bytes == len(payload)
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.source_path.read_bytes() == payload
    assert stored.source_path.is_relative_to(Path(settings.data_root) / "uploads")


@pytest.mark.asyncio
async def test_get_video_returns_persisted_status(upload_context) -> None:
    _, _repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        upload = await client.post(
            "/api/v1/videos",
            files={"file": ("lesson.webm", b"video", "video/webm")},
        )
        response = await client.get(f"/api/v1/videos/{upload.json()['video_id']}")

    assert response.status_code == 200
    assert response.json() == {
        "video_id": upload.json()["video_id"],
        "state": "QUEUED",
        "progress": 0,
        "error_code": None,
    }


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_media(upload_context) -> None:
    _, _repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("notes.txt", b"not video", "text/plain")},
        )

    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_rejects_empty_video(upload_context) -> None:
    settings, _repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("empty.mp4", b"", "video/mp4")},
        )

    assert response.status_code == 422
    assert list((Path(settings.data_root) / "uploads").iterdir()) == []


@pytest.mark.asyncio
async def test_upload_enforces_streaming_size_limit(upload_context) -> None:
    settings, repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("large.mp4", b"x" * (1024 * 1024 + 1), "video/mp4")},
        )

    assert response.status_code == 413
    assert list((Path(settings.data_root) / "uploads").iterdir()) == []
    assert repository.get_video_job(uuid4()) is None


@pytest.mark.asyncio
async def test_get_video_returns_404_for_unknown_id(upload_context) -> None:
    _, _repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/videos/{uuid4()}")

    assert response.status_code == 404
