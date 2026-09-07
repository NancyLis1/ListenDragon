# ListenDragon backend

FastAPI API 与后台任务 Worker 共用 `listen_dragon` 包。当前已实现健康检查、流式视频上传、上传大小与媒体类型校验、SHA-256 计算、隔离文件落盘、SQLite 视频任务持久化和状态查询，以及带租约的媒体处理流水线。

上传成功后任务依次经历 `QUEUED -> EXTRACTING -> TRANSCRIBING -> CHUNKING -> INDEXING -> READY/FAILED`。Worker 使用 FFprobe 校验视频时长、FFmpeg 提取 16 kHz 单声道 WAV、faster-whisper 生成带时间戳转写，随后切分文本并原子发布 FAISS/BM25 索引。路由不得直接调用 FFmpeg 或模型。

T12 已实现 `services.retrieval.LocalHybridRetriever` 和查询改写适配器。对 `READY` 视频调用 `search(video_id, query, limit=6)`，返回带原文、时间戳、chunk_id 和 RRF 分数的 `RetrievedChunk`。通过 `build_retriever(settings)` 构造并复用实例，避免每请求冷启动嵌入模型。同步调用不得直接阻塞异步路由；完整契约、错误码与验证命令见 [交接文档](../docs/t12-handoff.md)。

T13 新增 `POST /api/v1/conversations`、`POST /api/v1/conversations/{id}/messages` 和 `POST /api/v1/videos/{id}/summary`。问答采用结构化结论、引用白名单和独立证据核验；摘要覆盖全部 chunks，长内容分批综合并按索引版本缓存。会话、消息和助手证据持久化到 SQLite。完整请求/响应、配置和联调边界见 [T13 交接文档](../docs/t13-handoff.md)。

全栈联调增加课程列表、完整元数据、转写、Range 视频内容和跨视频检索 API。检索、问答共享应用级 `LocalHybridRetriever`，跨视频搜索只执行一次查询改写和向量编码。所有浏览器可见错误均使用 T13 的结构化错误格式。接口与无密钥运行行为见[全栈联调交接](../docs/fullstack-integration.md)。
