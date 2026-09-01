from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from listen_dragon.api.health import router as health_router
from listen_dragon.api.videos import router as videos_router
from listen_dragon.core.config import get_settings


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="ListenDragon API",
        version="0.1.0",
        description="Video transcription, hybrid retrieval and grounded QA API.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
    )
    app.include_router(health_router)
    app.include_router(videos_router, prefix="/api/v1")
    return app


app = create_app()
