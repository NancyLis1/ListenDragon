# 前后端完整联调交接

实现分支：`feat/fullstack-integration`。该分支包含 T13 提交并保留原作者信息，目标 PR 合并到 `main`；不会直接合并或自动关闭同事的 T13 PR。

## 浏览器闭环

前端启动后先检查 API，再读取后端持久化课程。存在 `READY` 课程时仅展示真实课程；后端离线或没有就绪课程时展示明确标记的体验样例。上传页会读取服务端上传限制并先在浏览器校验视频时长，后端再按 `MAX_VIDEO_MINUTES` 复核；完成后可刷新恢复课程、Range 播放源视频、查看带时间戳转写、跨课程搜索、按需生成摘要并进行持久化多轮问答。阅读页的问答栏在桌面端固定于视口并独立滚动，不会再被长转写撑高。

摘要和问答需要 OpenAI-compatible 模型。团队联调模型为 `qwen3.8-flash`，开发者只需在自己的 `.env` 填写 `LLM_BASE_URL` 和 `LLM_API_KEY`；密钥不得加入任何 `VITE_*` 变量。未配置密钥时，上传、转写、播放和本地混合检索仍可使用，摘要和问答返回明确的 `GENERATION_NOT_CONFIGURED`，不会生成伪答案。

## 新增资源 API

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| GET | `/api/v1/videos` | 按创建时间倒序列出持久化视频及状态 |
| GET | `/api/v1/videos/limits` | 获取上传大小与视频时长限制 |
| GET | `/api/v1/videos/{video_id}` | 获取文件元数据、时长和处理状态 |
| GET | `/api/v1/videos/{video_id}/transcript` | 获取 `READY` 视频的分段转写 |
| GET | `/api/v1/videos/{video_id}/content` | 支持 HTTP Range 的源视频播放 |
| POST | `/api/v1/search` | 在指定的 1–50 个 `READY` 视频中搜索 |

搜索请求示例：

```json
{
  "query": "课程如何解释相对位置？",
  "video_ids": ["<uuid>"],
  "limit": 20
}
```

响应结果包含 `video_id`、`original_name`、`chunk_id`、`start_ms`、`end_ms`、`text` 和 RRF `score`。跨视频检索复用一次问题改写与向量编码；RRF 分数只用于排序，不代表答案可信度。

## 验证

不带密钥的自动化测试不访问外网，LLM 使用 Stub 或 `MockTransport`：

```bash
python -m pip install -r backend/requirements-dev.lock
python -m pip install -e ./backend --no-deps
python -m ruff check backend
python -m pytest backend/tests -q
python -m pip check
cd frontend
npm ci
npm test
npm run build
```

配置真实 Qwen 后还需人工上传一个合法视频，等待 `READY`，刷新并依次验证播放、转写、搜索、摘要、连续追问和所有证据时间跳转。当前不包含鉴权、删除、翻译、流式回答或多 Worker 并发。
