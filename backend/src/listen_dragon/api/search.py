from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from listen_dragon.api.dependencies import get_retriever
from listen_dragon.api.errors import mapped_api_error
from listen_dragon.domain.models import SearchRequest, SearchResultView, SearchView
from listen_dragon.services.retrieval import LocalHybridRetriever, RetrievalError

router = APIRouter(tags=["search"])


@router.post("/search", response_model=SearchView)
async def search_videos(
    payload: SearchRequest,
    retriever: Annotated[LocalHybridRetriever, Depends(get_retriever)],
) -> SearchView:
    try:
        reports = await run_in_threadpool(
            retriever.search_many,
            [str(item) for item in payload.video_ids],
            payload.query,
            limit_per_video=min(6, payload.limit),
        )
    except RetrievalError as exc:
        raise mapped_api_error(exc.error_code) from exc

    videos = {item.video_id: item for item in retriever.repository.list_videos()}
    results = [
        SearchResultView(
            video_id=UUID(report.video_id),
            original_name=videos[UUID(report.video_id)].original_name,
            chunk_id=chunk.chunk_id,
            start_ms=chunk.start_ms,
            end_ms=chunk.end_ms,
            text=chunk.text,
            score=chunk.score,
        )
        for report in reports
        for chunk in report.chunks
    ]
    results.sort(key=lambda item: (-item.score, item.original_name.casefold(), item.start_ms))
    return SearchView(results=results[: payload.limit])
