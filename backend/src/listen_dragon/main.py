import re
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from listen_dragon.api.errors import ApiError, api_error_handler, validation_error_handler
from listen_dragon.api.generation import router as generation_router
from listen_dragon.api.health import router as health_router
from listen_dragon.api.search import router as search_router
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
        expose_headers=["Accept-Ranges", "Content-Length", "Content-Range", "X-Request-ID"],
    )
    app.add_exception_handler(ApiError, api_error_handler)  # type: ignore[arg-type]
    app.add_exception_handler(RequestValidationError, validation_error_handler)  # type: ignore[arg-type]

    @app.middleware("http")
    async def request_id_middleware(request: Request, call_next):
        supplied = request.headers.get("X-Request-ID", "")
        request_id = supplied if re.fullmatch(r"[A-Za-z0-9._-]{1,64}", supplied) else str(uuid4())
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response

    app.include_router(health_router)
    app.include_router(videos_router, prefix="/api/v1")
    app.include_router(generation_router, prefix="/api/v1")
    app.include_router(search_router, prefix="/api/v1")
    return app


app = create_app()
