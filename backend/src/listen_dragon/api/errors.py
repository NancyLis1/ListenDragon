from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from listen_dragon.domain.models import ApiErrorView


class ApiError(Exception):
    def __init__(
        self,
        *,
        status_code: int,
        error_code: str,
        message: str,
        retryable: bool = False,
        details: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(error_code)
        self.status_code = status_code
        self.error_code = error_code
        self.message = message
        self.retryable = retryable
        self.details = details


async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
    body = ApiErrorView(
        error_code=exc.error_code,
        message=exc.message,
        request_id=getattr(request.state, "request_id", "unknown"),
        retryable=exc.retryable,
        details=exc.details,
    )
    return JSONResponse(status_code=exc.status_code, content=body.model_dump(mode="json"))


async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details: list[dict[str, Any]] = [
        {"location": list(error.get("loc", ())), "type": error.get("type", "validation_error")}
        for error in exc.errors()
    ]
    body = ApiErrorView(
        error_code="INVALID_REQUEST",
        message="请求参数不合法。",
        request_id=getattr(request.state, "request_id", "unknown"),
        retryable=False,
        details=details,
    )
    return JSONResponse(status_code=422, content=body.model_dump(mode="json"))


_ERRORS: dict[str, tuple[int, str, bool]] = {
    "INVALID_QUERY": (422, "问题或检索参数不合法。", False),
    "VIDEO_NOT_FOUND": (404, "视频不存在或已删除。", False),
    "VIDEO_NOT_READY": (409, "视频尚未处理完成，请稍后重试。", True),
    "VIDEO_FILE_NOT_FOUND": (503, "视频源文件不可用。", True),
    "UNSUPPORTED_MEDIA_TYPE": (415, "不支持该视频格式。", False),
    "UPLOAD_TOO_LARGE": (413, "视频超过上传大小限制。", False),
    "UPLOAD_EMPTY": (422, "上传的视频为空。", False),
    "CONVERSATION_NOT_FOUND": (404, "会话不存在。", False),
    "CONVERSATION_CONFLICT": (409, "会话已被其他请求更新，请重试。", True),
    "INDEX_NOT_FOUND": (503, "视频索引不可用，需要重新构建。", True),
    "INDEX_VERSION_MISMATCH": (503, "视频索引版本不一致，需要重新构建。", True),
    "INDEX_CORRUPT": (503, "视频索引校验失败，需要重新构建。", True),
    "EMBEDDING_MODEL_MISMATCH": (503, "检索模型与索引不匹配。", False),
    "EMBEDDING_DIMENSION_MISMATCH": (503, "检索向量维度与索引不匹配。", False),
    "RETRIEVAL_DEPENDENCY_UNAVAILABLE": (503, "检索依赖暂不可用。", True),
    "EMBEDDING_FAILED": (503, "问题向量化失败。", True),
    "RETRIEVAL_FAILED": (503, "视频证据检索失败。", True),
    "GENERATION_NOT_CONFIGURED": (503, "问答模型尚未配置。", False),
    "LLM_AUTH_ERROR": (503, "问答模型鉴权失败，请检查服务端配置。", False),
    "LLM_RATE_LIMITED": (503, "问答模型繁忙，请稍后重试。", True),
    "LLM_TIMEOUT": (503, "问答模型响应超时，请稍后重试。", True),
    "LLM_UNAVAILABLE": (503, "问答模型暂不可用。", True),
    "LLM_INVALID_RESPONSE": (503, "模型返回内容未通过证据校验。", True),
}


def mapped_api_error(error_code: str) -> ApiError:
    status_code, message, retryable = _ERRORS.get(error_code, (503, "服务暂不可用。", True))
    return ApiError(
        status_code=status_code,
        error_code=error_code,
        message=message,
        retryable=retryable,
    )
