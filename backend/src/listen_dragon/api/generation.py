from __future__ import annotations

import threading
from pathlib import Path
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from starlette.concurrency import run_in_threadpool

from listen_dragon.api.dependencies import get_retriever
from listen_dragon.api.errors import mapped_api_error
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.domain.models import (
    AnswerView,
    ConversationCreate,
    ConversationCreated,
    ConversationView,
    MessageCreate,
    SummaryRequest,
    SummaryView,
)
from listen_dragon.infrastructure.sqlite_conversations import SqliteConversationRepository
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url
from listen_dragon.infrastructure.vision import FrameAnalyzer
from listen_dragon.services.grounded_generation import (
    GroundedGenerationService,
    ServiceError,
    build_generation_service,
)
from listen_dragon.services.llm_generation import GenerationError, OpenAITextGenerator
from listen_dragon.services.retrieval import LocalHybridRetriever, RetrievalError

router = APIRouter(tags=["generation"])
_SERVICE_LOCK = threading.Lock()


def get_generation_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    retriever: Annotated[LocalHybridRetriever, Depends(get_retriever)],
) -> GroundedGenerationService:
    cache_key = (
        settings.database_url,
        settings.data_root,
        settings.embedding_model,
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.llm_timeout_seconds,
        settings.llm_max_response_bytes,
        settings.retrieval_top_k,
        settings.retrieval_rrf_k,
        settings.query_expansion_enabled,
        settings.query_expansion_timeout_seconds,
        settings.generation_context_chars,
        settings.conversation_memory_chars,
        settings.vision_enabled, settings.vision_model, settings.ffmpeg_binary,
        settings.vision_max_frames, settings.vision_short_video_seconds, settings.vision_interval_seconds,
    )
    if getattr(request.app.state, "generation_service_key", None) != cache_key:
        with _SERVICE_LOCK:
            if getattr(request.app.state, "generation_service_key", None) != cache_key:
                database_path = sqlite_path_from_url(settings.database_url)
                jobs = SqliteJobRepository(database_path)
                jobs.initialize()
                conversations = SqliteConversationRepository(database_path)
                conversations.initialize()
                generator = OpenAITextGenerator(
                    base_url=settings.llm_base_url,
                    api_key=settings.llm_api_key,
                    model=settings.llm_model,
                    timeout_seconds=settings.llm_timeout_seconds,
                    max_response_bytes=settings.llm_max_response_bytes,
                    memory_chars=settings.conversation_memory_chars,
                )
                request.app.state.generation_service = build_generation_service(
                    jobs=jobs,
                    conversations=conversations,
                    retriever=retriever,
                    generator=generator,
                    context_chars=settings.generation_context_chars,
                    memory_chars=settings.conversation_memory_chars,
                    visual_reader=FrameAnalyzer(OpenAITextGenerator(
                        base_url=settings.llm_base_url, api_key=settings.llm_api_key,
                        model=settings.vision_model or settings.llm_model,
                        timeout_seconds=max(60, settings.llm_timeout_seconds),
                    ), ffmpeg_binary=settings.ffmpeg_binary,
                        interval_seconds=settings.vision_interval_seconds,
                        max_frames=settings.vision_max_frames) if settings.vision_enabled else None,
                    data_root=Path(settings.data_root),
                    short_video_ms=round(settings.vision_short_video_seconds * 1000),
                )
                request.app.state.generation_service_key = cache_key
    return request.app.state.generation_service


@router.post(
    "/videos/{video_id}/summary",
    response_model=SummaryView,
    status_code=status.HTTP_200_OK,
)
async def summarize_video(
    video_id: UUID,
    options: SummaryRequest,
    service: Annotated[GroundedGenerationService, Depends(get_generation_service)],
) -> SummaryView:
    try:
        return await run_in_threadpool(service.summarize, video_id, options)
    except (RetrievalError, GenerationError, ServiceError) as exc:
        raise mapped_api_error(exc.error_code) from exc


@router.post(
    "/conversations",
    response_model=ConversationCreated,
    status_code=status.HTTP_201_CREATED,
)
async def create_conversation(
    payload: ConversationCreate,
    service: Annotated[GroundedGenerationService, Depends(get_generation_service)],
) -> ConversationCreated:
    try:
        return await run_in_threadpool(service.create_conversation, payload.video_id)
    except (RetrievalError, GenerationError, ServiceError) as exc:
        raise mapped_api_error(exc.error_code) from exc


@router.get("/conversations/{conversation_id}", response_model=ConversationView)
async def read_conversation(
    conversation_id: UUID,
    service: Annotated[GroundedGenerationService, Depends(get_generation_service)],
) -> ConversationView:
    try:
        return await run_in_threadpool(service.get_conversation, conversation_id)
    except ServiceError as exc:
        raise mapped_api_error(exc.error_code) from exc


@router.post(
    "/conversations/{conversation_id}/messages",
    response_model=AnswerView,
    status_code=status.HTTP_200_OK,
)
async def ask_question(
    conversation_id: UUID,
    payload: MessageCreate,
    service: Annotated[GroundedGenerationService, Depends(get_generation_service)],
) -> AnswerView:
    try:
        return await run_in_threadpool(service.ask, conversation_id, payload.question)
    except (RetrievalError, GenerationError, ServiceError) as exc:
        raise mapped_api_error(exc.error_code) from exc
