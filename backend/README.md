# ListenDragon backend

FastAPI API 与后台任务 Worker 共用 `listen_dragon` 包。当前已实现健康检查、流式视频上传、上传大小、媒体类型与视频时长校验、SHA-256 计算、隔离文件落盘、SQLite 视频任务持久化和状态查询，以及带租约的媒体处理流水线。上传接口会在创建任务前按 `MAX_VIDEO_MINUTES` 校验时长，Worker 保留同一校验作为兜底。

上传成功后任务依次经历 `QUEUED -> EXTRACTING -> TRANSCRIBING -> VISUALIZING -> CHUNKING -> INDEXING -> READY/FAILED`。上传路由只在线程池中使用 FFprobe 读取媒体元数据；Worker 使用 FFmpeg 提取 16 kHz 单声道 WAV、faster-whisper 生成带时间戳转写，再使用有序画面分析事件，随后切分文本并原子发布 FAISS/BM25 索引。禁用视觉时跳过 VISUALIZING。同步 FFmpeg、模型调用必须在线程池/Worker 中运行，不阻塞异步路由。

T12 已实现 `services.retrieval.LocalHybridRetriever` 和查询改写适配器。对 `READY` 视频调用 `search(video_id, query, limit=6)`，返回带原文、时间戳、chunk_id 和 RRF 分数的 `RetrievedChunk`。通过 `build_retriever(settings)` 构造并复用实例，避免每请求冷启动嵌入模型。同步调用不得直接阻塞异步路由；完整契约、错误码与验证命令见 [交接文档](../docs/t12-handoff.md)。

T13 新增 `POST /api/v1/conversations`、`POST /api/v1/conversations/{id}/messages` 和 `POST /api/v1/videos/{id}/summary`。问答采用结构化结论、引用白名单和独立证据核验；摘要覆盖全部 chunks，长内容分批综合并按索引版本缓存。会话、消息和助手证据持久化到 SQLite。完整请求/响应、配置和联调边界见 [T13 交接文档](../docs/t13-handoff.md)。

全栈联调增加课程列表、完整元数据、转写、Range 视频内容和跨视频检索 API。检索、问答共享应用级 `LocalHybridRetriever`，跨视频搜索只执行一次查询改写和向量编码。所有浏览器可见错误均使用 T13 的结构化错误格式。接口与无密钥运行行为见[全栈联调交接](../docs/fullstack-integration.md)。

新版视觉工作流增加 `GET/POST /api/v1/videos/{id}/visual-analysis`。旧 READY 视频可补分析；分段检查点复用已完成窗口；状态中包含视觉版本、分析时间和语音告警。开启视觉时，缺少新版视觉结果的摘要/QA 返回 `VISION_ANALYSIS_REQUIRED`，不会把处理缺失伪装为内容无依据。详见[配置、复现与验收](../docs/video-workflow-validation.md)。
