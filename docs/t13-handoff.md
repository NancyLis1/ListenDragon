# T13：对话式 QA 与视频摘要 API 交接

后端工程师：孟月涵；实现分支：`codex/t13-grounded-qa-summary`。

## 交付内容

T13 在 T12 混合检索之上新增了可持久化的多轮问答与全局摘要链路：

- 会话严格绑定一个 `READY` 视频；用户消息、助手消息、助手证据和摘要化会话记忆写入 SQLite。
- 每轮追问都重新执行 T12 检索。会话记忆只用于消解“它/这个方法”等指代，不作为视频事实证据。
- 模型输出必须是结构化“结论 + evidence_id”。后端只接受本次检索结果中的 evidence_id，并根据数据库中的真实时间范围生成引用，模型不能自行指定时间戳。
- 候选答案和最终摘要还会经过一次独立的证据支持核验；不受引用片段直接支持的结论会被移除，答案结论全部移除时返回固定拒答，摘要要点全部移除时拒绝缓存和返回该摘要。
- 摘要读取该视频的全部已发布 chunks。超出上下文预算时按时间顺序分批摘要，再做全局去重与综合；结果按 `video_id + index_version + 参数` 缓存，索引更新后不会误用旧摘要。
- 同一会话的并发写入使用 revision 乐观并发控制，避免两个慢模型请求覆盖彼此的会话记忆或打乱消息顺序。
- 模型调用使用线程池，不阻塞 FastAPI 异步事件循环；供应商响应有超时、体积、状态码、JSON schema 和引用集合校验。

## API

### 创建会话

```http
POST /api/v1/conversations
Content-Type: application/json

{"video_id":"<uuid>"}
```

成功返回 `201`：

```json
{
  "conversation_id": "<uuid>",
  "video_id": "<uuid>",
  "created_at": "2026-09-07T12:00:00Z"
}
```

### 提问

```http
POST /api/v1/conversations/{conversation_id}/messages
Content-Type: application/json

{"question":"视频中的课题分离是什么意思？"}
```

成功返回 `200`。`answer` 的每条结论带服务器生成的 `[mm:ss-mm:ss]`，`evidence` 同时提供可供前端点击跳转的结构化毫秒时间与原始转写片段：

```json
{
  "conversation_id": "<uuid>",
  "message_id": "<uuid>",
  "answer": "…… [03:08-04:27]",
  "refused": false,
  "evidence": [
    {
      "chunk_id": "<chunk-id>",
      "video_id": "<uuid>",
      "start_ms": 188580,
      "end_ms": 267400,
      "timestamp": "[03:08-04:27]",
      "text": "<原始转写片段>"
    }
  ],
  "created_at": "2026-09-07T12:00:05Z"
}
```

证据不足时仍返回 `200`，但 `refused=true`、`evidence=[]`，并使用固定拒答文案。这和模型/索引故障不同；后者返回明确的 503 错误码。

### 生成摘要

```http
POST /api/v1/videos/{video_id}/summary
Content-Type: application/json

{"language":"auto","length":"medium","format":"outline"}
```

- `language`：`auto`、`zh-CN`、`en`
- `length`：`short`、`medium`、`detailed`
- `format`：`outline`、`paragraphs`

成功返回 `200 summary + evidence[]`。`cached=true` 表示命中当前索引版本的持久化摘要。

## 配置

QA/摘要不会在缺少模型配置时伪造降级答案。需在后端 `.env` 配置 OpenAI-compatible 服务：

```dotenv
LLM_BASE_URL=https://example.com/v1
LLM_API_KEY=<仅存本地或部署 Secret>
LLM_MODEL=qwen3.8-flash
LLM_TIMEOUT_SECONDS=30
LLM_MAX_RESPONSE_BYTES=1048576
GENERATION_CONTEXT_CHARS=24000
CONVERSATION_MEMORY_CHARS=1200
```

密钥不得写入前端变量、日志、数据库、文档或 Git。T12 查询扩展在无密钥时可回退到原问题，但 T13 最终生成会返回 `GENERATION_NOT_CONFIGURED`，不会绕过证据链。

## 错误契约

T13 参数校验和业务错误统一返回：

```json
{
  "error_code": "VIDEO_NOT_READY",
  "message": "视频尚未处理完成，请稍后重试。",
  "request_id": "<request-id>",
  "retryable": true,
  "details": null
}
```

主要映射：参数错误 422；视频/会话不存在 404；视频未就绪或会话并发冲突 409；索引损坏、嵌入失败、模型未配置、超时、限流、鉴权失败或生成结果未通过校验 503。响应不包含供应商响应体、密钥、文件路径或完整提示词。

## 验证

自动化测试不请求外网、不需要真实密钥，使用 Stub/`httpx.MockTransport` 覆盖正常链路和故障分支：

```powershell
python -m ruff check backend
python -m pytest backend/tests -q
python -m pip check
cd frontend
npm run build
```

覆盖的 T13 关键场景包括：SQLite 会话/证据持久化、消息顺序、并发冲突、多轮指代上下文、结构化引用、伪时间戳清除、无依据拒答、二次证据核验、长摘要分批综合、索引版本缓存、Prompt 注入文本隔离、无配置、超时、限流、鉴权失败、重定向、超大/畸形响应和统一 API 错误。

## 已知边界与联调建议

- 当前接口是同步 JSON 响应，符合架构接口表中的 `200 summary/answer` 契约；PRD 中的 SSE/WebSocket 首字流式体验尚未加入。若前端要做逐字流式展示，应另立接口版本，不能让未核验 token 直接流给用户。
- 二次模型核验能降低无依据结论风险，但不能证明绝对正确。正式验收仍需用独立、不可回答问题集检查拒答率和引用支持率。
- T12 的 RRF 分数不是概率，因此 T13 没有虚构一个未经校准的固定阈值。是否可回答由严格提示、结构化引用白名单和独立证据核验共同决定；后续有独立标注集后再校准数值阈值。
- 前端应使用 `evidence.start_ms` 跳转播放器，不要解析 `answer` 字符串来恢复时间；回答文字中的时间戳用于人读和复制。
