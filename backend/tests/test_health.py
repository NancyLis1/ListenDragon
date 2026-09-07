import httpx
import pytest

from listen_dragon.core.config import Settings, get_settings
from listen_dragon.main import app


@pytest.mark.asyncio
async def test_live_health() -> None:
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/health/live")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_ready_checks_database_configuration() -> None:
    app.dependency_overrides[get_settings] = lambda: Settings(
        _env_file=None, database_url="postgresql://unsupported", data_root="/tmp"
    )
    transport = httpx.ASGITransport(app=app)
    try:
        async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/health/ready")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 503
    assert response.json()["error_code"] == "NOT_READY"
