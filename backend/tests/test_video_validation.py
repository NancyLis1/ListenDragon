from pathlib import Path

import httpx
import pytest

from listen_dragon.api.videos import get_job_repository, get_media_extractor
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.main import app


class ValidMediaProbe:
    def probe_duration(self, _video: Path) -> float:
        return 12.5


@pytest.fixture
def validation_context(tmp_path: Path):
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
    app.dependency_overrides[get_media_extractor] = lambda: ValidMediaProbe()
    yield settings, repository
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_upload_rejects_extension_and_mime_mismatch(validation_context) -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("lesson.mp4", b"video", "video/webm")},
        )
    assert response.status_code == 415


@pytest.mark.asyncio
async def test_upload_normalizes_uppercase_extension(validation_context) -> None:
    _settings, repository = validation_context
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("LESSON.MP4", b"video", "video/mp4")},
        )
    assert response.status_code == 202
    stored = repository.get_stored_video(response.json()["video_id"])
    assert stored is not None
    assert stored.source_path.suffix == ".mp4"


@pytest.mark.asyncio
async def test_upload_strips_directory_components_from_filename(validation_context) -> None:
    settings, repository = validation_context
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("../../中文课程.mp4", b"video", "video/mp4")},
        )
    assert response.status_code == 202
    stored = repository.get_stored_video(response.json()["video_id"])
    assert stored is not None
    assert stored.original_name == "中文课程.mp4"
    assert stored.source_path.is_relative_to(Path(settings.data_root) / "uploads")
