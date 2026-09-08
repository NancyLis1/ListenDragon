# 真实全链路验证记录（2026-09-08）

基线：从远端同步 `main` 至 `02a1fd6`（PR #4），修复分支 `codex/real-e2e-validation`。没有重复合并 PR #3。Computer Use 的浏览器连接先前失败；经用户同意，本次改用 agent-browser 0.27.0 驱动独立 Chrome 实例，并用 HTTP 请求、真实 Worker 日志和自动化测试交叉验证。本文不将这种替代方式称为 Computer Use 已通过。

## 实测环境与材料

- Windows 原生运行：Python 3.12、FastAPI API、单 Worker、SQLite、FFmpeg/FFprobe 9.0.1、React/Vite。没有 Docker/WSL 可用，未验证容器环境。
- ASR：本地 faster-whisper base；向量模型：本地 multilingual MiniLM；真实 FAISS/BM25 索引。CPU 运行，未使用转写、检索或生成 Stub。
- `.env` 仅由应用自身加载；没有读取或输出其内容、密钥或完整运行时配置。模型配置不进入前端。新增测试用例使用假的模型响应，真实浏览器链路使用现有 Qwen 配置，两者分开计数。
- 用户相机素材：原 AVI 30 秒，复制转码为 H.264/AAC MP4（1,503,554 字节）；原文件未修改。AVI 不在当前上传格式列表，直接选择时正确拒绝。
- 第二份材料：[Blender 官方 Sintel 预告片](https://download.blender.org/durian/trailer/sintel_trailer-480p.mp4)，52.208 秒、4,372,373 字节。不是长视频。
- Hugging Face 下载曾返回 429；本机用 ModelScope 的对应模型文件完成缓存，并用显式本地模型路径、离线加载完成后续实测。未更改项目默认模型或依赖锁文件。

## 实测结果

| 项目 | 实际证据与结论 |
| --- | --- |
| 上传、后台处理、轮询 | 两份有效 MP4 均从浏览器上传（202），经真实 Worker 到 READY；前端轮询后自动打开阅读页。相机样本得到 8 段转写、1 个 chunk；预告片 2 段、1 个 chunk。短暂中间状态可能被一秒轮询间隔跳过，Worker 日志确认各处理阶段运行。 |
| 播放 | 两份视频实际播放；生产页面预告片 `currentTime` 从 0 推进到 27.728 秒，`paused=false`、`readyState=4`、`error=null`，解码尺寸 854×480；已检查截图。 |
| HTTP Range | 两份素材分别请求首 1024 字节和末 1024 字节，均为 206、响应体 1024 字节且 Content-Range 正确；超出文件范围返回 416、空响应体及 `bytes */总字节数`。 |
| 转写 | READY 后 API 200，浏览器显示实际分段；预告片的两句对白与问题及时间范围一致。相机噪声素材存在明显可疑识别词，不视为转写准确率通过。 |
| 搜索 | 真实搜索返回带视频 ID、chunk 与时间范围的结果。`gatekeepers` 首条为预告片，点击“从此处播放”实际跳到 11.92 秒；也返回了弱相关相机片段，见风险。 |
| 摘要 | 两份视频均经真实 Qwen 生成并显示证据；预告片摘要的引用按钮实际跳到 11.92 秒。服务重启后重新请求两份摘要均为 200、`cached=true`。 |
| 新建会话、多轮问答 | 浏览器显式创建会话（201），相机视频连续两轮真实有据回答复用同一会话；点击回答证据实际跳到 1.36 秒。再次新建会话清空当前界面，旧会话 GET 仍保留 8 条消息。 |
| 无依据拒答 | 相机问题“飞船发动机型号是什么”返回拒答且无引用；预告片先正确回答来访目的是找人，再问具体找谁时拒答，因为对白没有提供身份。 |
| 转写跳转 | 点击预告片第二句转写，实际 `video.currentTime=14.42` 秒。 |
| 重启恢复 | 实际停止 API 和 Worker，随后使用相同 SQLite、上传文件及索引重启；刷新浏览器恢复先前选择的旧视频，而不是最新上传。原三轮 6 条会话消息恢复，继续提问后旧会话持久化增至 8 条。该重启后追问返回拒答；不能据此宣称复杂指代正确率通过。 |
| 浏览器错误 | 正常链路无未处理 JS 错误；生产构建页面重新清空诊断记录后检查，错误与控制台日志为空。故障注入产生的网络失败与正常操作分开记录。 |
| 异常提示 | 停止 API 后搜索显示“无法连接后端服务”；把播放器资源改为不存在的 UUID 触发真实 404，页面显示视频加载失败。损坏 MP4 上传后到 FAILED/INVALID_MEDIA，有中文提示；同文件可以重新选择。 |
| 其他 API 边界 | 不存在会话返回 404/CONVERSATION_NOT_FOUND；空搜索请求返回 422。 |

## 缺陷与修复

1. **Windows 中文路径无法写入/读取 FAISS 索引。** 原生 FAISS 文件接口在含“中文+空格”的仓库路径失败，真实上传到 INDEX_BUILD_FAILED。改用 Python 文件读写与 FAISS 序列化/反序列化，保持原有索引发布流程。增加真实 FAISS 中文目录往返检索测试，修复后两份视频成功建索引，服务重启后也能加载使用。
2. **Windows 媒体错误输出解码异常。** 损坏视频令 FFprobe 输出 UTF-8 路径，默认 GBK 解码抛出子线程 UnicodeDecodeError。FFmpeg/FFprobe 现在显式 UTF-8 且替换非法字节；新增两项真实子进程测试。重启 Worker 后再上传同一损坏文件，只产生预期 INVALID_MEDIA 日志，无解码异常。
3. **刷新丢失当前课程/会话展示，缺少显式新建会话入口。** 新增只读会话历史 API；浏览器仅存储当前视频 ID 与各视频会话 ID，刷新从 SQLite 恢复消息及引用。增加新建会话按钮、恢复期间禁用输入、恢复失败保护，避免静默替换旧会话；课程切换重新挂载阅读器。补 API 重开仓库、旧课程选择、历史恢复和新会话回归。
4. **取消搜索后永久显示“正在检索”。** 清空输入时复位状态，忽略已取消请求的晚到响应；真实浏览器复现和复测通过。真实课程不再自动发送样例问题，搜索输入和侧栏按钮有明确可访问名称。
5. **真实视频被配上虚构的课程封面。** 上传视频的搜索卡片/预览改为明确的上传视频占位图，避免出现“The Scientific Method”等样例内容；补回归。
6. **失败反馈与文件重选不完整。** 增加处理错误说明及播放器错误提示，同一文件可再次选择，清理轮询监听器；不能解析的时长显示“时长待校验”，小文件显示实际 B/KB，不再虚报 1 分钟/1 MB。补对应回归。

## 最终自动检查

| 检查 | 结果 |
| --- | --- |
| `python -m pytest backend/tests -q` | 126 passed；包含真实 FAISS 用例及真实子进程编码用例 |
| `python -m ruff check backend` | All checks passed |
| `python -m pip check` | No broken requirements found |
| `npm test -- --run`（frontend） | 24 passed，6 个测试文件 |
| `npm run build`（frontend） | TypeScript 与 Vite 生产构建通过，45 modules |
| `npm ls --depth=0`（frontend） | 退出码 0，无缺失依赖 |
| 生产构建浏览器冒烟 | Vite preview 使用构建产物，课程恢复、播放、摘要、证据跳转及既有问答展示通过 |

FAISS 回归在未安装 `backend[ai]` 的轻量环境会 skip；本机安装 AI 依赖，最终 126 项没有 skip。依赖检查表示安装关系完整，不等于做过漏洞审计；没有修改锁文件或宣称依赖安全审计通过。

## 未关闭风险与未验证范围

- 相机短片噪声较多、识别内容有误；“回答有转写引用”不意味着引用准确反映原始音频。尚未做人工标注/WER 评估，也未更换大模型做质量对比。
- 搜索目前返回 top-k 候选，RRF 分数不是置信度；跨视频搜索含弱相关结果。需要标注集评估排序/阈值后再改策略，不能随意增加阈值而损伤语义召回。
- 两份素材各仅 1 个 chunk。长课程、多 chunk 摘要、复杂长期对话、超过大小/时长边界的真实文件、多 Worker 并发、处理中崩溃租约恢复和性能负载没有实测。部分边界只有自动化测试覆盖。
- Windows Uvicorn/asyncio Proactor 在浏览器取消/切换视频连接时出现过 `ConnectionResetError [WinError 10054]` 回调日志。后续 Range、API 和页面仍工作；本次没有修复或隐藏该运行时日志。
- 新历史 API 一次返回完整会话，超长会话尚无分页；系统原本没有鉴权，本次仍是本机测试部署。生产公网部署、GitHub Pages 到后端的跨域链路及 Docker 镜像没有验证。
- 本机依赖、模型镜像和 FFmpeg 与 Docker/锁定环境不完全相同；不能把本机结果外推为容器环境已通过。Computer Use 浏览器连接问题仍未解决。

## 复现步骤

1. 在包含本次修复的分支安装后端 core/dev/ai 依赖和前端 `npm ci`，准备 FFmpeg/FFprobe、完整 ASR/向量模型文件。保留后端既有 `.env`，不要读取/输出其内容或把密钥配置到 `VITE_*`。
2. 本机测试辅助启动器保存在仓库旁的 `../tmp/e2e-tools/start_local.py`，可分别在两个终端从仓库根目录执行：

   ```powershell
   .venv/Scripts/python.exe ../tmp/e2e-tools/start_local.py api
   .venv/Scripts/python.exe ../tmp/e2e-tools/start_local.py worker
   ```

   该辅助文件和素材属于本地测试产物，不随 Git 提交。其他机器按下方通用方式启动，在 API 与 Worker 两个终端分别设置相同环境变量；尖括号路径需替换为已准备的真实路径：

   ```powershell
   $env:DATA_ROOT = Join-Path (Get-Location) 'data'
   $env:DATABASE_URL = 'sqlite:///data/listendragon.db'
   $env:CORS_ORIGINS = 'http://localhost:5173,http://127.0.0.1:5173'
   $env:ASR_MODEL = '<完整 ASR 模型目录>'
   $env:EMBEDDING_MODEL = '<完整 SentenceTransformer 模型目录>'
   $env:FFMPEG_BINARY = '<ffmpeg.exe 路径>'
   $env:FFPROBE_BINARY = '<ffprobe.exe 路径>'
   $env:HF_HUB_OFFLINE = '1'
   # API 终端
   .venv/Scripts/python.exe -m uvicorn listen_dragon.main:app --host 127.0.0.1 --port 8000
   # Worker 终端（在另一个终端执行）
   .venv/Scripts/python.exe -m listen_dragon.worker
   ```

3. 前端终端运行以下命令，然后打开 `http://localhost:5173/ListenDragon/`：

   ```powershell
   cd frontend
   npm run build
   node node_modules/vite/bin/vite.js preview --host 127.0.0.1 --port 5173 --strictPort
   ```

4. 上传 MP4，等待 READY 自动进入阅读页；验证播放、转写、摘要。在预告片提问 `Why did the visitor come here?`，再问 `Who are they searching for?`；前者应引用“找人”的对白，后者应拒绝补造身份。点击引用核对播放器实际时间，而不只看按钮文案。
5. 到搜索页输入 `gatekeepers`，打开预告片匹配结果；在检索过程中清空输入，确认恢复课程列表并结束加载状态。
6. 保留数据库和 data 文件，停止 API/Worker 后重启；刷新阅读页，核对课程、转写、摘要缓存与会话历史，再创建新会话并用 GET 验证旧会话仍存在。
7. 异常用例：直接选择 AVI；上传仅含文本的 `.mp4`；暂时停止 API 后搜索；将播放器源改为不存在视频的 content URL 触发 404，随后刷新恢复。不要把这些故意触发的错误计为正常链路错误。

本地额外证据：`../tmp/e2e-tools/live-verification.json`（状态、Range、缓存和消息数量，不含密钥/转写正文），`production-reader.png`（生产页面截图）。用户视频、转写、数据库、索引、模型和截图均未纳入 Git。
