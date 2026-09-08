# ListenDragon 视频助手

ListenDragon 是“奶龙也是龙”团队的进阶项目一实现仓库。系统提供视频上传、语音转写、画面事件分析、摘要与带时间戳引用的多轮问答。

## 架构摘要

- `frontend/`：React + TypeScript + Vite；静态产物部署到 GitHub Pages。
- `backend/`：FastAPI API 与后台 Worker 共用一套 Python 代码。
- `data/`：本地开发数据卷；上传文件、转写产物、FAISS/BM25 索引均不进入 Git。
- `.github/workflows/`：CI 与 GitHub Pages 部署。

GitHub Pages 只能托管静态前端。浏览器通过 `VITE_API_BASE_URL` 访问独立部署或本机运行的后端，模型密钥只保存在后端环境变量中。

## 快速开始

1. 复制 `.env.example` 为 `.env`，按需填写模型配置。
2. 运行 `docker compose --profile dev up --build`。
3. 前端访问 `http://localhost:5173/ListenDragon/`，API 文档访问 `http://localhost:8000/docs`。
4. 运行 `powershell -ExecutionPolicy Bypass -File scripts/verify-env.ps1` 获取环境证据。

当前已完成上传、任务轮询、持久化课程列表、Range 视频播放、转写、跨视频混合检索、摘要和带时间戳证据的多轮问答闭环。后端离线或课程库为空时，前端会显示明确标记的体验样例；真实课程不会与样例混合。详见 [T12 检索交接](docs/t12-handoff.md)、[T13 QA/摘要交接](docs/t13-handoff.md)和[全栈联调交接](docs/fullstack-integration.md)。

视频理解采用 Qwen 官方有序帧协议。Worker 按重叠窗口提取事件；短视频概括/摘要读取全片覆盖的画面与转写，细节问答定位事件后加密回看原始画面，核验阶段同样读取画面。新上传默认分析画面；已有视频在播放器下方点击“开始音画分析”。视觉接口不读取音轨，语音仍来自本地 ASR。配置、能力边界与实测记录见[视频工作流交接](docs/video-workflow-validation.md)，设计依据见[调研记录](docs/video-workflow-research.md)。

完整 AI 镜像按 CPU/INT8 基线构建：Dockerfile 从 PyTorch 官方 CPU wheel 索引预装 `torch==2.6.0`，避免默认解析 CUDA 运行时。宿主机无需单独安装 FFmpeg，容器内已固化并验证 FFmpeg 7.1.5。

## 分支与提交约定

- 默认分支：`main`
- 功能分支：`feat/<scope>`；修复分支：`fix/<scope>`
- 提交信息：Conventional Commits，例如 `feat(api): add video upload endpoint`
- 受保护信息：`.env`、上传视频、模型缓存、索引与数据库不得提交

## 目录

```text
ListenDragon/
├─ backend/                 FastAPI 与 Worker
├─ frontend/                React/Vite 静态前端
├─ docs/adr/                架构决策记录
├─ scripts/                 环境验证脚本
├─ data/                    本地数据卷（仅保留目录）
├─ compose.yaml             本地一致性环境
└─ .github/workflows/       CI 与 Pages 发布
```
