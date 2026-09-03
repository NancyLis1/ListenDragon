import { useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { Icon } from "../../components/Icon";
import { processingSteps } from "../../data/mockLectures";
import { uploadVideo, type BackendStatus } from "../../lib/api";
import type { ProcessingStep } from "../../types/lecture";
import { ProcessingSteps } from "./ProcessingSteps";

interface UploadPageProps {
  backend: BackendStatus;
}

const acceptedTypes = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
const maxFileSize = 500 * 1024 * 1024;

function formatFileSize(bytes: number) {
  return bytes >= 1024 * 1024 * 1024 ? `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB` : `${Math.max(1, Math.round(bytes / 1024 / 1024))} MB`;
}

export function UploadPage({ backend }: UploadPageProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [steps, setSteps] = useState<ProcessingStep[]>(processingSteps);
  const [message, setMessage] = useState("支持 MP4、WebM、MOV、MKV；单文件不超过 500 MB。");
  const [isUploading, setIsUploading] = useState(false);

  const selectFile = (file?: File) => {
    if (!file) return;
    if (!acceptedTypes.includes(file.type)) {
      setMessage("请选择 MP4、WebM、MOV 或 MKV 格式的视频文件。");
      return;
    }
    if (file.size > maxFileSize) {
      setMessage("当前文件超过 500 MB 的 MVP 限制，请选择更小的视频。");
      return;
    }
    setSelectedFile(file);
    setMessage(`已选择 ${file.name}（${formatFileSize(file.size)}），可以开始解析。`);
    setSteps(processingSteps.map((step, index) => index === 0 ? { ...step, title: "文件已就绪", description: `${file.name} · ${formatFileSize(file.size)}`, state: "complete", detail: "待上传" } : { ...step, state: "pending", detail: "等待中" }));
  };

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0]);
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  const beginUpload = async () => {
    if (!selectedFile || isUploading) return;
    if (backend !== "online") {
      setMessage("后端当前未连接，文件未离开浏览器。启动 API 服务后即可提交解析任务。");
      return;
    }
    setIsUploading(true);
    setMessage("正在提交解析任务…");
    try {
      await uploadVideo(selectedFile);
      setMessage("任务已提交。转写、检索和摘要会按进度逐步可用。");
      setSteps(processingSteps.map((step, index) => index === 0 ? { ...step, description: `${selectedFile.name} · ${formatFileSize(selectedFile.size)}`, detail: "刚刚" } : index === 1 ? { ...step, state: "working", title: "正在转写", description: "正在识别视频中的语音", detail: "进行中" } : { ...step, state: "pending", detail: "等待中" }));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "视频上传失败，请稍后重试。");
    } finally {
      setIsUploading(false);
    }
  };

  return (
    <main className="upload-page page-content">
      <div className="upload-main">
        <header className="page-heading">
          <h1>课程视频解析</h1>
          <p>上传课程视频，提取转写、幻灯片文字和关键摘要。</p>
        </header>
        <section
          className={`drop-zone ${isDragging ? "is-dragging" : ""} ${selectedFile ? "has-file" : ""}`}
          onDragEnter={(event) => { event.preventDefault(); setIsDragging(true); }}
          onDragOver={(event) => event.preventDefault()}
          onDragLeave={() => setIsDragging(false)}
          onDrop={handleDrop}
          aria-label="视频文件上传区域"
        >
          <Icon name="upload" className="drop-icon" />
          <h2>{selectedFile ? selectedFile.name : "拖拽视频文件到这里"}</h2>
          <p>{message}</p>
          <input ref={inputRef} type="file" accept={acceptedTypes.join(",")} onChange={handleInput} />
          <button className="outline-button" type="button" onClick={() => inputRef.current?.click()}>选择文件</button>
          {selectedFile && <button className="primary-button upload-submit" type="button" onClick={() => void beginUpload()} disabled={isUploading}>{isUploading ? "正在提交…" : "开始解析"}</button>}
        </section>
        <ProcessingSteps steps={steps} />
      </div>
      <aside className="upload-aside">
        <section className="file-summary" aria-label="当前文件">
          <h2>文件</h2>
          <div className="file-preview"><span className="preview-play"><Icon name="play" /></span><span>Lecture Reader<br />视频预览</span></div>
          <strong>{selectedFile?.name || "lecture-05-introduction.mp4"}</strong>
          <p>{selectedFile ? formatFileSize(selectedFile.size) : "1.2 GB"} · 1:23:45</p>
        </section>
        <section className="info-callout"><Icon name="info" /><p>转写和幻灯片处理完成后即可开始检索，无需等待全部任务结束。</p></section>
        <p className={`backend-status backend-status--${backend}`}>服务状态：{backend === "online" ? "已连接" : backend === "checking" ? "检测中" : "未连接"}</p>
      </aside>
    </main>
  );
}
