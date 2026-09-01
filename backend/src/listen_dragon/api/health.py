from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health/live")
def live() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/ready")
def ready() -> dict[str, str]:
    # 后续加入数据库可写、数据目录可写和模型就绪检查。
    return {"status": "ready"}
