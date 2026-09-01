import { useEffect, useState } from "react";

const apiBase = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000/api/v1";
const healthUrl = apiBase.replace(/\/api\/v1\/?$/, "/health/live");

export default function App() {
  const [backend, setBackend] = useState<"checking" | "online" | "offline">("checking");

  useEffect(() => {
    fetch(healthUrl)
      .then((response) => setBackend(response.ok ? "online" : "offline"))
      .catch(() => setBackend("offline"));
  }, []);

  return (
    <main className="shell">
      <header className="hero">
        <p className="eyebrow">奶龙也是龙 · 视频内容理解</p>
        <h1>ListenDragon</h1>
        <p className="lead">上传视频，获得可追溯的转写、摘要与带时间戳引用的问答。</p>
        <p className={`status status-${backend}`}>后端状态：{backend}</p>
      </header>

      <section className="upload" aria-labelledby="upload-title">
        <h2 id="upload-title">上传视频</h2>
        <p>支持 MP4、WebM、MOV、MKV；MVP 单文件不超过 500 MB、60 分钟。</p>
        <input type="file" accept="video/mp4,video/webm,video/quicktime,video/x-matroska" />
        <button type="button" disabled={backend !== "online"}>开始解析</button>
        {backend === "offline" && <p className="hint">请先启动独立后端；GitHub Pages 不运行模型服务。</p>}
      </section>
    </main>
  );
}
