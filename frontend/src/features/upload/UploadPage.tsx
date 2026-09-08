import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { Icon } from "../../components/Icon";
import { processingSteps } from "../../data/mockLectures";
import { ApiError, getVideo, uploadVideo, type ApiVideo, type BackendStatus, type JobState } from "../../lib/api";
import type { ProcessingStep } from "../../types/lecture";
import { formatTimestamp } from "../reader/LectureVideo";
import { ProcessingSteps } from "./ProcessingSteps";

interface UploadPageProps {
  backendStatus: BackendStatus;
  onComplete: (video: ApiVideo) => void;
}

const acceptedTypes = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
const acceptedExtensions = [".mp4", ".webm", ".mov", ".mkv"];
const maxFileSize = 500 * 1024 * 1024;
const fallbackDurationMs = 0;
const processingErrors: Record<string, string> = {
  ASR_FAILED: "语音识别失败，请检查服务端模型是否已下载及模型服务是否可用，然后重新选择视频上传。",
  ASR_UNAVAILABLE: "服务端缺少语音识别组件，请安装后重新上传。",
  ASR_EMPTY: "未识别到可转写的语音，请选择包含清晰讲话的视频。",
  INVALID_MEDIA: "文件无法识别为有效视频，请检查文件是否损坏。",
  FFMPEG_FAILED: "音频提取失败，请确认视频包含可用音轨。",
  VIDEO_TOO_LONG: "视频超过服务端时长限制，请截取较短片段后上传。",
  INDEX_BUILD_FAILED: "检索索引构建失败，请检查服务端模型及存储后重新上传。",
};
const stateStep: Partial<Record<JobState, number>> = {
  QUEUED: 1,
  EXTRACTING: 1,
  TRANSCRIBING: 2,
  CHUNKING: 3,
  INDEXING: 4,
};

export function formatFileSize(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return bytes >= 1024 * 1024 * 1024
    ? `${(bytes / 1024 / 1024 / 1024).toFixed(1)} GB`
    : `${Math.max(1, Math.round(bytes / 1024 / 1024))} MB`;
}

function hasAcceptedFormat(file: File) {
  if (file.type) return acceptedTypes.includes(file.type);
  const lowerName = file.name.toLowerCase();
  return acceptedExtensions.some((extension) => lowerName.endsWith(extension));
}

export function readVideoDuration(file: File): Promise<number> {
  if (typeof URL.createObjectURL !== "function") return Promise.resolve(fallbackDurationMs);
  return new Promise((resolve) => {
    const temporaryUrl = URL.createObjectURL(file);
    const video = document.createElement("video");
    let settled = false;
    let timeoutId: number | undefined;
    const finish = (durationMs: number) => {
      if (settled) return;
      settled = true;
      if (timeoutId !== undefined) window.clearTimeout(timeoutId);
      video.removeAttribute("src");
      URL.revokeObjectURL(temporaryUrl);
      resolve(durationMs);
    };
    video.preload = "metadata";
    video.onloadedmetadata = () => finish(
      Number.isFinite(video.duration) && video.duration > 0
        ? Math.round(video.duration * 1000)
        : fallbackDurationMs,
    );
    video.onerror = () => finish(fallbackDurationMs);
    timeoutId = window.setTimeout(() => finish(fallbackDurationMs), 1500);
    video.src = temporaryUrl;
    video.load();
  });
}

function stepsForJob(file: File | null, job?: ApiVideo): ProcessingStep[] {
  const failedStep = job?.state === "FAILED"
    ? job.progress <= 10 ? 1 : job.progress <= 30 ? 2 : job.progress <= 55 ? 3 : 4
    : undefined;
  const active = failedStep ?? (job ? stateStep[job.state] : undefined);
  return processingSteps.map((step, index) => {
    let state: ProcessingStep["state"] = "pending";
    let detail = "等待中";
    if (job?.state === "READY" || active !== undefined && index < active) {
      state = "complete";
      detail = "已完成";
    } else if (active === index) {
      state = job?.state === "FAILED" ? "failed" : "working";
      detail = job?.state === "FAILED" ? "失败" : `${job?.progress ?? 0}%`;
    }
    return {
      ...step,
      description: index === 0 && file ? `${file.name} · ${formatFileSize(file.size)}` : step.description,
      state,
      detail,
    };
  });
}

function waitForPoll(signal: AbortSignal) {
  return new Promise<void>((resolve, reject) => {
    const abort = () => {
      window.clearTimeout(timer);
      reject(new DOMException("Aborted", "AbortError"));
    };
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", abort);
      resolve();
    }, 1000);
    signal.addEventListener("abort", abort, { once: true });
  });
}

export function UploadPage({ backendStatus, onComplete }: UploadPageProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const controllerRef = useRef<AbortController | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [durationMs, setDurationMs] = useState(fallbackDurationMs);
  const [steps, setSteps] = useState<ProcessingStep[]>(processingSteps);
  const [message, setMessage] = useState("支持 MP4、WebM、MOV、MKV；单文件不超过 500 MB。");
  const [isProcessing, setIsProcessing] = useState(false);
  const [jobId, setJobId] = useState<string>();
  const [canRetry, setCanRetry] = useState(false);

  useEffect(() => () => controllerRef.current?.abort(), []);

  const selectFile = (file?: File) => {
    controllerRef.current?.abort();
    setIsProcessing(false);
    setCanRetry(false);
    setJobId(undefined);
    if (!file) return;
    if (!hasAcceptedFormat(file)) {
      setSelectedFile(null);
      setSteps(stepsForJob(null));
      setMessage("请选择 MP4、WebM、MOV 或 MKV 格式的视频文件。");
      return;
    }
    if (file.size > maxFileSize) {
      setSelectedFile(null);
      setSteps(stepsForJob(null));
      setMessage("当前文件超过 500 MB 限制，请选择更小的视频。");
      return;
    }
    setSelectedFile(file);
    setDurationMs(fallbackDurationMs);
    setSteps(stepsForJob(file));
    setMessage(`已选择 ${file.name}（${formatFileSize(file.size)}），可以开始上传。`);
    void readVideoDuration(file).then(setDurationMs);
  };

  const monitorJob = async (id: string, controller: AbortController) => {
    while (!controller.signal.aborted) {
      const job = await getVideo(id, controller.signal);
      setSteps(stepsForJob(selectedFile, job));
      setMessage(`后端处理中：${job.state}（${job.progress}%）`);
      if (job.state === "READY") {
        setMessage("处理完成，正在打开课程阅读页。");
        onComplete(job);
        return;
      }
      if (job.state === "FAILED") {
        const code = job.error_code || "UNKNOWN";
        throw new ApiError(`${processingErrors[code] || "视频处理失败，请检查服务端日志后重新上传。"}（${code}）`, 409, code);
      }
      await waitForPoll(controller.signal);
    }
  };

  const runMonitor = async (id: string) => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsProcessing(true);
    setCanRetry(false);
    try {
      await monitorJob(id, controller);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMessage(error instanceof Error ? error.message : "查询处理状态失败。");
      setCanRetry(error instanceof ApiError ? error.retryable || error.status === 0 : true);
    } finally {
      if (!controller.signal.aborted) setIsProcessing(false);
    }
  };

  const beginProcessing = async () => {
    if (!selectedFile || isProcessing) return;
    if (backendStatus === "offline") {
      setMessage("后端服务未连接，请启动 API 和 Worker 后重试。");
      return;
    }
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;
    setIsProcessing(true);
    setCanRetry(false);
    setMessage("正在上传视频…");
    let acceptedId: string | undefined;
    try {
      const accepted = await uploadVideo(selectedFile, controller.signal);
      acceptedId = accepted.video_id;
      setJobId(accepted.video_id);
      setSteps((current) => current.map((step, index) => index === 0
        ? { ...step, state: "complete", detail: "已完成" }
        : step));
      await monitorJob(accepted.video_id, controller);
    } catch (error) {
      if (controller.signal.aborted) return;
      setMessage(error instanceof Error ? error.message : "视频上传失败，请稍后重试。");
      setCanRetry(Boolean(acceptedId) && (error instanceof ApiError ? error.retryable || error.status === 0 : true));
    } finally {
      if (!controller.signal.aborted) setIsProcessing(false);
    }
  };

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => {
    selectFile(event.target.files?.[0]);
    event.target.value = ""; // Allow selecting the same file again after a failed job.
  };
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  return (
    <main className="upload-page page-content">
      <div className="upload-main">
        <header className="page-heading"><h1>课程视频解析</h1><p>上传课程视频，生成真实转写、检索索引、摘要和问答。</p></header>
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
          <p aria-live="polite">{message}</p>
          <input ref={inputRef} type="file" accept={acceptedTypes.join(",")} onChange={handleInput} />
          <button className="outline-button" type="button" onClick={() => inputRef.current?.click()} disabled={isProcessing}>选择文件</button>
          {selectedFile && !jobId && <button className="primary-button upload-submit" type="button" onClick={() => void beginProcessing()} disabled={isProcessing}>{isProcessing ? "正在上传…" : "开始解析"}</button>}
          {jobId && canRetry && <button className="primary-button upload-submit" type="button" onClick={() => void runMonitor(jobId)} disabled={isProcessing}>继续查询状态</button>}
        </section>
        <ProcessingSteps steps={steps} />
      </div>
      <aside className="upload-aside">
        <section className="file-summary" aria-label="当前文件">
          <h2>文件</h2>
          <div className="file-preview"><span className="preview-play"><Icon name="play" /></span><span>Lecture Reader<br />后端持久化</span></div>
          <strong>{selectedFile?.name || "尚未选择视频"}</strong>
          <p>{selectedFile ? `${formatFileSize(selectedFile.size)} · ${durationMs > 0 ? formatTimestamp(durationMs) : "时长待校验"}` : "选择文件后显示信息"}</p>
        </section>
        <section className="info-callout"><Icon name="info" /><p>视频会上传至配置的 ListenDragon 后端，并在处理完成后持久保存。</p></section>
        <p className={`backend-status backend-status--${backendStatus}`}>后端状态：{backendStatus === "online" ? "已连接" : backendStatus === "offline" ? "离线" : "检查中"}</p>
      </aside>
    </main>
  );
}
