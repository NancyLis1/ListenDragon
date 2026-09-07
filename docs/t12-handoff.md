# T12：多查询扩展与检索融合交接

系统工程师：李乐妍；验证日期：2026-09-07。

## 当前结论与边界

T07–T11 已由 PR #1 合入 main（0230a95），本轮从该提交创建 `feat/t12-hybrid-retriever`，没有重复合并同学分支。T12 服务实现、单元/对抗性测试及真实 Video1/Qwen 验证已完成，可供 T13 接入；PR 审核/合并状态以 GitHub 为准。

这不是“整个网页已具备完整功能”的验收。当前前端聊天/摘要仍有模拟数据；T13 的回答生成、摘要、上下文预算、拒答、HTTP 接口、前端引用跳转和 T15/T16 综合测试不在本轮完成范围。

## 提供给 T13 的稳定接口

```python
from listen_dragon.core.config import Settings
from listen_dragon.services.retrieval import build_retriever

retriever = build_retriever(Settings())  # 应在应用生命周期中构造并复用
chunks = retriever.search(video_id, question, limit=6)
# 每条：chunk_id, start_ms, end_ms, text, score
```

`search` 与既有 `HybridRetriever` Protocol 兼容。诊断用 `search_detailed(..., mode="vector"|"hybrid"|"multi")` 增加 video_id、index_version、queries、fallback_reason、elapsed_ms。只有 `multi` 请求云端改写。接口同步且包含模型/网络 I/O，应使用同步路由或 `run_in_threadpool`，不能直接阻塞 async 事件循环。

输入问题规范化后限 1–1000 字符；limit 为 1–50 整数；默认每路 Top-8、RRF k=60、输出 Top-6。最多三个查询（含原问题），同时在 FAISS 归一化内积与 BM25 中召回，按一基名次 `Σ1/(60+rank)` 融合并以 chunk_id 去重。结果可能少于 limit，不补造数据。

结果保留索引原始时间戳和原文，不做相邻块拼接。RRF score 仅表示排序票数，不是概率，也不是可回答性判据。T13 必须绑定请求视频、校验证据支持关系，并实现问题超出视频范围时的拒答。

## 配置与安全

| 配置 | 默认 | 含义 |
| --- | --- | --- |
| LLM_BASE_URL / LLM_MODEL / LLM_API_KEY | 空 | 本次实测 Qwen qwen3.8-flash；用户专属地址及密钥仅本地 .env |
| QUERY_EXPANSION_ENABLED | true | 关闭后完全使用原问题 |
| QUERY_EXPANSION_TIMEOUT_SECONDS | 8 | HTTPX 各网络阶段超时，不是端到端总时长 SLA |
| RETRIEVAL_TOP_K | 8 | 每查询每召回渠道候选数 |
| RETRIEVAL_RRF_K | 60 | RRF 排名平滑常数 |

LLM 返回最多解析 64 KiB；不自动重定向、不进行自动网络重试。超时、401/403/429/5xx、格式错误和截断回复回退原问题，理由仅为枚举码，不返回供应商错误体。原问题总会保留，但提示词不能保证改写绝不发生语义漂移。

视频、转写全文、数据库、索引、模型和密钥不提交 Git。查询改写只发送当前问题，不发送视频或全文；新增评测问题本轮获得用户明确授权。前端 Compose 仅接收两项 VITE 变量，不再继承整份后端 .env。索引为本地可信产物，禁止接收外部上传的 pickle 或让不可信用户写数据卷；哈希不能将任意 pickle 变安全。视频范围隔离不是身份鉴权，公网部署仍需鉴权/限流/TLS。

## 错误契约

| error_code | T13 建议处理 |
| --- | --- |
| INVALID_QUERY | 映射 400/422，要求合法 UUID、问题和 limit |
| VIDEO_NOT_FOUND | 404 |
| VIDEO_NOT_READY | 409，前端继续展示处理状态 |
| INDEX_NOT_FOUND / INDEX_VERSION_MISMATCH / INDEX_CORRUPT | 明确检索不可用；通知运维检查、重建索引，禁止生成无依据答案 |
| EMBEDDING_MODEL_MISMATCH / EMBEDDING_DIMENSION_MISMATCH | 对齐模型配置并重建索引 |
| RETRIEVAL_DEPENDENCY_UNAVAILABLE / EMBEDDING_FAILED / RETRIEVAL_FAILED | 503；内部日志只保留必要诊断，响应使用脱敏码 |

这些是服务异常，不是本轮新增的 HTTP 路由。查询改写失败通常不会抛出上述异常，原查询仍可完成本地混合检索。

## 可复现命令

仓库根目录，后端测试不下载模型、不请求 Qwen：

```powershell
python -m pip install -e "./backend[dev]"
python -m ruff check backend
python -m pytest backend/tests -q
```

真实服务需 AI extra 或完整 Docker 镜像，以及已处理到 READY 的视频。常规环境使用 `.env`/`data/`；本轮另用 `.tmp_t12` 隔离环境与 18000 端口，未改正式项目数据卷。

```powershell
docker compose exec -T api python -m listen_dragon.retrieve <video_id> --query "什么是课题分离？" --limit 3
```

命令行不打印转写全文；JSON 输出可用 `--output` 写入容器可写位置，已存在文件会拒绝覆盖。评测 fixture 是 Video1 特定时间窗口，不是可套用到任意视频的金标准。

```powershell
python -m listen_dragon.retrieve <video_id> --evaluate backend/tests/fixtures/video1_retrieval_queries.json --output local-result.json
# 明确允许该测试集问题发送到配置的云端服务时才加 --include-cloud
```

评测默认只有本地 vector/hybrid，只有显式加 `--include-cloud` 才评测 multi。宿主机调用时需把 DATA_ROOT/DATABASE_URL 指向宿主机目录，不能沿用容器 /data 路径。容器中需只读挂载 fixture；镜像不默认包含测试集。

## 实际验证证据

- 原始视频：Video1.mp4，12,671,078 bytes，329.77 秒。
- 新验收任务：`6fac2137-a800-4b99-8d70-c38f16eacdab`，READY/100%，115 条转写、5 个分块。
- 索引版本：`26f8d69c444f3349`；manifest、各文件哈希、数据库分块映射、维度及计数由真实检索加载器全部校验通过。
- Whisper revision：`ebe41f70d5b6dfa9166e2c581c45c9c0cfc57b66`；MiniLM revision：`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`。均从官方 Hugging Face 仓库下载至隔离缓存；检索评测使用 HF_HUB_OFFLINE=1。
- 使用已有 CPU AI 镜像搭载当前源码只读挂载验证：torch 2.6.0+cpu、faster-whisper 1.2.1、sentence-transformers 5.7.0、faiss 1.15.0。没有发布新的 T12 容器镜像；部署方应按仓库 Dockerfile 重建。
- 首次任务 `5801879c-4c16-4ab5-83a2-818110506e9c` 因模型源 SSL 超时失败；模型缓存下载成功后以新任务复验通过，未篡改 FAILED 状态。
- 自动化：74 passed；Ruff、pip check、Compose config 和前端 Vite 构建通过。coverage 的行/分支综合覆盖率：query_expansion 100%、retrieval 95%、合计 96%；不是整个后端覆盖率。

用户 Q1/Q2 在三种模式的 Top-1 均命中。Q1 定义的 ASR 答案窗口 195380–200500 ms，返回分块为 188580–267400 ms；Q2 答案窗口 148620–177580 ms，返回分块为 128220–200500 ms。窗口基于转写内容核对，未逐帧验证 ASR 时间戳。

### 20 题开发集对照

两个问题为用户提供；其余 18 题由助手基于本次转写构造并标注，非独立/留出测试集。正确分块定义为完整包含标注答案窗口。Hit@k 表示至少一个正确分块命中；Recall@3 表示全部正确分块的召回比例；MRR@3 为首个正确结果名次的倒数。五个分块中 Top-5 会失去区分力，因此报告 Top-1/3。

| 模式 | Hit@1 | Hit@3 | Recall@3 | MRR@3 | 热态中位 ms | 最大 ms |
| --- | --- | --- | --- | --- | --- | --- |
| 纯向量 | 70% | 100% | 95% | 0.842 | 104.7 | 152.0 |
| 原问题双路 RRF | 80% | 95% | 95% | 0.867 | 106.3 | 128.3 |
| 多查询双路 RRF | 95% | 95% | 92.5% | 0.950 | 870.7 | 2114.5 |

完整逐题结果见 `evidence/t12-evaluation.json`。冷启动单列，不计入热态；此样本不用于宣称 P95、10k 分块性能或普遍质量达标。一次 `no_rewrites` 回退：Qwen 没给新增查询，原问题成功命中，不是网络失败。

## 对抗性审查与未关闭事项

| 发现/反例 | 本轮处置 | 后续负责人/条件 |
| --- | --- | --- |
| 云端超时、限流、异常 JSON/超大回复可能破坏主链路 | 自动化验证原问题回退；不泄露响应体 | 系统/后端，监控失败比率 |
| 损坏索引、模型错配、跨视频分块映射 | 校验失败即停止；两视频隔离、错版本/维度/哈希测试通过 | T13 不得吞异常并继续无证据生成 |
| 前端容器继承后端密钥 | Compose 改为仅传入 VITE_* 两项 | 已修正 |
| SQLite WAL/SHM、环境变体误提交 | 补充 .gitignore | 已修正；提交前复核 |
| Q17 在双路/多查询 Top-3 漏检，纯向量第 2 位命中 | 保留真实反例，不修改标签掩盖；默认 Top-6 在本视频会包含全部 5 块，不能据此掩盖排序问题 | 系统+测试：独立集复验后决定原查询权重/召回策略 |
| ASR 繁简混合与错字；LLM 可能添加背景或弱化语义 | 保留原文和原问题，报告残余风险，不声称解决 | 后端+测试：评估更大 ASR、简繁归一化和改写约束 |
| RRF 必然返回近邻，不代表答案有依据 | 明确划归 T13 证据判断/拒答 | 后端/测试，需不可回答问题用例 |
| 同步模型调用、无独立负载测试 | 明确线程池使用与实例复用 | T13/T15/T16 验证并发、内存、延迟 |
| Worker 续租/fencing、删除、幂等复用和完整 AI 锁定尚不完备 | 不越界修改前序架构；本轮仅单 Worker 正常链路通过 | 系统+后端，综合验收前处理或书面接受 |

本轮结论：T12 **实现可移交，质量结论有限**。Q17 和真实转写质量需在综合测试中继续跟踪；没有以阶段完成代替系统最终验收。
