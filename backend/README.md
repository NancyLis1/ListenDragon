# ListenDragon backend

FastAPI API 与后台任务 Worker 共用 `listen_dragon` 包。当前骨架提供健康检查、任务状态模型和服务接口；后续实现必须保持 API/领域/基础设施分层，不允许路由直接调用 FFmpeg 或模型。
