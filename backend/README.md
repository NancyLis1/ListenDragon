# ListenDragon backend

FastAPI API 与后台任务 Worker 共用 `listen_dragon` 包。当前已实现健康检查、流式视频上传、上传大小与媒体类型校验、SHA-256 计算、隔离文件落盘、SQLite 视频任务持久化和状态查询，以及带租约的媒体处理流水线。

上传成功后任务依次经历 `QUEUED -> EXTRACTING -> TRANSCRIBING -> CHUNKING -> INDEXING -> READY/FAILED`。Worker 使用 FFprobe 校验视频时长、FFmpeg 提取 16 kHz 单声道 WAV、faster-whisper 生成带时间戳转写，随后切分文本并原子发布 FAISS/BM25 索引。路由不得直接调用 FFmpeg 或模型。
