from __future__ import annotations

import threading
from typing import Annotated

from fastapi import Depends, Request

from listen_dragon.core.config import Settings, get_settings
from listen_dragon.services.retrieval import LocalHybridRetriever, build_retriever

_RETRIEVER_LOCK = threading.Lock()


def get_retriever(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> LocalHybridRetriever:
    cache_key = (
        settings.database_url,
        settings.data_root,
        settings.embedding_model,
        settings.llm_base_url,
        settings.llm_model,
        settings.llm_api_key,
        settings.retrieval_top_k,
        settings.retrieval_rrf_k,
        settings.query_expansion_enabled,
        settings.query_expansion_timeout_seconds,
    )
    if getattr(request.app.state, "retriever_key", None) != cache_key:
        with _RETRIEVER_LOCK:
            if getattr(request.app.state, "retriever_key", None) != cache_key:
                request.app.state.retriever = build_retriever(settings)
                request.app.state.retriever_key = cache_key
    return request.app.state.retriever
