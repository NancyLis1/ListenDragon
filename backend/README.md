# ListenDragon backend

FastAPI API 与后台任务 Worker 共用 `listen_dragon` 包。当前已实现健康检查、流式视频上传、上传大小与媒体类型校验、SHA-256 计算、隔离文件落盘、SQLite 视频任务持久化和状态查询，以及带租约的 FFmpeg 音频提取任务。

上传成功后任务进入 `QUEUED`。Worker 领取任务后用 FFprobe 校验视频时长，并提取 16 kHz 单声道 WAV；成功后进入 `TRANSCRIBING`，等待 Whisper 处理。路由不得直接调用 FFmpeg 或模型。
