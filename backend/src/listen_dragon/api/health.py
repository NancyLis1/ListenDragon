import tempfile
import sqlite3
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends

from listen_dragon.api.errors import ApiError
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready(settings: Annotated[Settings, Depends(get_settings)]) -> dict[str, str]:
    try:
        repository = SqliteJobRepository(sqlite_path_from_url(settings.database_url))
        repository.initialize()
        data_root = Path(settings.data_root)
        data_root.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(dir=data_root):
            pass
    except (OSError, ValueError, sqlite3.Error) as exc:
        raise ApiError(
            status_code=503,
            error_code="NOT_READY",
            message="数据库或数据目录不可用。",
            retryable=True,
        ) from exc
    return {"status": "ready"}
