# ListenDragon 视频助手

ListenDragon 是“奶龙也是龙”团队的进阶项目一实现仓库。系统面向学习、访谈和会议视频，提供上传、转写、可选翻译、摘要与带时间戳引用的多轮问答。

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

当前阶段交付的是 T03/T05 所需的架构决策、代码骨架和环境验证入口；媒体处理、检索与问答服务保留清晰接口，由后续迭代实现。

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
