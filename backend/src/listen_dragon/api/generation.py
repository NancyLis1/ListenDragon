from __future__ import annotations

import threading
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Request, status
from starlette.concurrency import run_in_threadpool

from listen_dragon.api.errors import mapped_api_error
from listen_dragon.core.config import Settings, get_settings
from listen_dragon.domain.models import (
    AnswerView,
    ConversationCreate,
    ConversationCreated,
    MessageCreate,
    SummaryRequest,
    SummaryView,
)
from listen_dragon.infrastructure.sqlite_conversations import SqliteConversationRepository
from listen_dragon.infrastructure.sqlite_jobs import SqliteJobRepository, sqlite_path_from_url
from listen_dragon.services.grounded_generation import (
    GroundedGenerationService,
    ServiceError,
    build_generation_service,
)
from listen_dragon.services.llm_generation import GenerationError, OpenAITextGenerator
from listen_dragon.services.retrieval import RetrievalError, build_retriever

router = APIRouter(tags=["generation"])
_SERVICE_LOCK = threading.Lock()


def get_generation_service(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
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
                    retriever=build_retriever(settings),
                    generator=generator,
                    context_chars=settings.generation_context_chars,
                    memory_chars=settings.conversation_memory_chars,
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
