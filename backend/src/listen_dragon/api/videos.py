from typing import Annotated
from uuid import UUID, uuid4

from fastapi import APIRouter, File, HTTPException, UploadFile, status

from listen_dragon.domain.models import JobState, VideoJobAccepted, VideoJobView

router = APIRouter(prefix="/videos", tags=["videos"])


@router.post("", response_model=VideoJobAccepted, status_code=status.HTTP_202_ACCEPTED)
async def upload_video(file: Annotated[UploadFile, File()]) -> VideoJobAccepted:
    allowed = {"video/mp4", "video/webm", "video/quicktime", "video/x-matroska"}
    if file.content_type not in allowed:
        raise HTTPException(status_code=415, detail="Unsupported video media type")
    # 骨架阶段不落盘；T07 实现时必须流式写入、计算 SHA-256 并执行大小限制。
    return VideoJobAccepted(video_id=uuid4(), state=JobState.queued)


@router.get("/{video_id}", response_model=VideoJobView)
def get_video(video_id: UUID) -> VideoJobView:
    # T07 接入 SQLite 后替换为真实状态查询。
    return VideoJobView(video_id=video_id, state=JobState.queued, progress=0)
