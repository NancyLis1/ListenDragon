# ADR-003：GitHub Pages 仅承载静态前端

- 状态：接受
- 日期：2026-09-01
- 决策人：李乐妍（系统工程师）

## 决策

React/Vite 构建产物部署至 `https://NancyLis1.github.io/ListenDragon/`。前端通过构建变量 `VITE_API_BASE_URL` 指向独立后端；模型密钥和视频文件不得进入前端构建或 Git 仓库。

## 后果

- 必须配置 HTTPS 后端与精确 CORS 白名单。
- GitHub Pages 不承担上传、FFmpeg、ASR、索引或 LLM 推理。
- 本地演示可将 API 指向 `http://localhost:8000/api/v1`；公网演示必须另行部署后端。
