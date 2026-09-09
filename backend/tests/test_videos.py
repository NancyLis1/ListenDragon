import hashlib
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest

from listen_dragon.api.videos import get_job_repository, get_media_extractor
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.domain.models import JobState, VisualAnalysisView, VisualObservation
from listen_dragon.infrastructure.media import MediaProcessingError
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository
from listen_dragon.main import app
from listen_dragon.services.contracts import TranscriptSegment


class ValidMediaProbe:
    def probe_duration(self, _video: Path) -> float:
        return 12.5


class TooLongMediaProbe:
    def probe_duration(self, _video: Path) -> float:
        raise MediaProcessingError("VIDEO_TOO_LONG", "too long")


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
    app.dependency_overrides[get_media_extractor] = lambda: ValidMediaProbe()
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
    assert stored.duration_ms == 12_500
    assert stored.sha256 == hashlib.sha256(payload).hexdigest()
    assert stored.source_path.read_bytes() == payload
    assert stored.source_path.is_relative_to(Path(settings.data_root) / "uploads")


@pytest.mark.asyncio
async def test_visual_reanalysis_is_scoped_atomic_and_persistent(upload_context):
    settings, repository = upload_context
    settings.llm_base_url = "https://example.test/v1"
    settings.llm_api_key = "test-key"
    settings.llm_model = "test-model"
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        uploaded = await client.post("/api/v1/videos", files={"file": ("clip.mp4", b"video", "video/mp4")})
        video_id = UUID(uploaded.json()["video_id"])
        repository.set_video_duration(video_id, 30000)
        repository.update_job(video_id, state=JobState.ready, progress=100)
        path = f"/api/v1/videos/{video_id}/visual-analysis"
        assert (await client.get(path)).json()["status"] == "not_requested"
        assert (await client.post(path)).status_code == 202
        assert (await client.post(path)).status_code == 409
        assert (await client.get(path)).json()["status"] == "pending"
        assert (await client.get(f"/api/v1/videos/{uuid4()}/visual-analysis")).status_code == 404
        repository.save_visual_analysis(video_id, VisualAnalysisView(status="ready", observations=[
            VisualObservation(timestamp_ms=4000, text="西瓜分成两半"),
        ]))
        repository.update_job(video_id, state=JobState.ready, progress=100)
        reopened = SqliteJobRepository(repository.database_path)
        assert reopened.get_visual_analysis(video_id).observations[0].timestamp_ms == 4000
        assert "test-key" not in (await client.get(path)).text


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
        "original_name": "lesson.webm",
        "mime": "video/webm",
        "size_bytes": 5,
        "duration_ms": 12_500,
        "created_at": response.json()["created_at"],
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
async def test_upload_rejects_video_over_configured_duration(upload_context) -> None:
    settings, repository = upload_context
    settings.max_video_minutes = 60
    app.dependency_overrides[get_media_extractor] = lambda: TooLongMediaProbe()
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/videos",
            files={"file": ("long.mp4", b"video", "video/mp4")},
        )

    assert response.status_code == 422
    assert response.json()["error_code"] == "VIDEO_TOO_LONG"
    assert response.json()["message"] == "视频时长超过 60 分钟上传限制。"
    assert list((Path(settings.data_root) / "uploads").iterdir()) == []
    assert repository.list_videos() == []


@pytest.mark.asyncio
async def test_upload_limits_reflect_server_settings(upload_context) -> None:
    settings, _repository = upload_context
    settings.max_upload_mb = 321
    settings.max_video_minutes = 45
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/videos/limits")

    assert response.status_code == 200
    assert response.json() == {"max_upload_mb": 321, "max_video_minutes": 45}


@pytest.mark.asyncio
async def test_get_video_returns_404_for_unknown_id(upload_context) -> None:
    _, _repository = upload_context
    transport = httpx.ASGITransport(app=app)

    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get(f"/api/v1/videos/{uuid4()}")

    assert response.status_code == 404
    assert response.json()["error_code"] == "VIDEO_NOT_FOUND"


@pytest.mark.asyncio
async def test_list_transcript_and_range_content(upload_context) -> None:
    _settings, repository = upload_context
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        upload = await client.post(
            "/api/v1/videos",
            files={"file": ("lesson.mp4", b"0123456789", "video/mp4")},
        )
        video_id = UUID(upload.json()["video_id"])
        repository.set_video_duration(video_id, 12_500)
        repository.replace_transcript_segments(
            video_id, [TranscriptSegment(1000, 2500, "真实转写", "zh")]
        )
        repository.update_job(video_id, state=JobState.ready, progress=100)

        listing = await client.get("/api/v1/videos")
        transcript = await client.get(f"/api/v1/videos/{video_id}/transcript")
        content = await client.get(
            f"/api/v1/videos/{video_id}/content", headers={"Range": "bytes=2-5"}
        )

    assert listing.json()["items"][0]["duration_ms"] == 12_500
    assert transcript.json()["segments"] == [{
        "seq": 0, "start_ms": 1000, "end_ms": 2500, "text": "真实转写", "language": "zh"
    }]
    assert content.status_code == 206
    assert content.content == b"2345"
    assert content.headers["content-range"] == "bytes 2-5/10"


@pytest.mark.asyncio
async def test_transcript_requires_ready_video(upload_context) -> None:
    _settings, _repository = upload_context
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        upload = await client.post(
            "/api/v1/videos", files={"file": ("lesson.mp4", b"video", "video/mp4")}
        )
        response = await client.get(f"/api/v1/videos/{upload.json()['video_id']}/transcript")

    assert response.status_code == 409
    assert response.json()["error_code"] == "VIDEO_NOT_READY"
