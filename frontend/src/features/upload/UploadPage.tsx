import { useEffect, useRef, useState, type ChangeEvent, type DragEvent } from "react";

import { Icon } from "../../components/Icon";
import { processingSteps } from "../../data/mockLectures";
import type { LectureDetail, ProcessingStep, TranscriptSegment } from "../../types/lecture";
import { formatTimestamp } from "../reader/LectureVideo";
import { ProcessingSteps } from "./ProcessingSteps";

interface UploadPageProps {
  onComplete: (lecture: LectureDetail) => void;
}

const acceptedTypes = ["video/mp4", "video/webm", "video/quicktime", "video/x-matroska"];
const acceptedExtensions = [".mp4", ".webm", ".mov", ".mkv"];
const maxFileSize = 500 * 1024 * 1024;
const fallbackDurationMs = 60_000;

export function formatFileSize(bytes: number) {
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
    video.onloadedmetadata = () => {
      const durationMs = Number.isFinite(video.duration) && video.duration > 0
        ? Math.round(video.duration * 1000)
        : fallbackDurationMs;
      finish(durationMs);
    };
    video.onerror = () => finish(fallbackDurationMs);
    timeoutId = window.setTimeout(() => finish(fallbackDurationMs), 1500);
    video.src = temporaryUrl;
    video.load();
  });
}

export function createUploadedLecture(file: File, durationMs: number, videoUrl: string): LectureDetail {
  const safeDuration = Math.max(1000, durationMs || fallbackDurationMs);
  const at = (ratio: number) => Math.round(safeDuration * ratio);
  const title = file.name.replace(/\.[^.]+$/, "") || "本地课程视频";
  const segments: TranscriptSegment[] = [
    { id: `${title}-demo-1`, startMs: at(0.05), endMs: at(0.2), content: "这是用于展示时间跳转和转写高亮的演示片段，不代表视频的实际语音内容。" },
    { id: `${title}-demo-2`, startMs: at(0.2), endMs: at(0.42), content: "纯前端模式会保留本地视频播放，但不会上传文件或执行自动语音识别。" },
    { id: `${title}-demo-3`, startMs: at(0.42), endMs: at(0.65), content: "点击任意时间戳，可以观察播放器、转写、摘要章节和问答引用之间的联动。" },
    { id: `${title}-demo-4`, startMs: at(0.65), endMs: at(0.84), content: "真实服务接入后，这些区域将由转写、检索和摘要接口返回的数据替换。" },
    { id: `${title}-demo-5`, startMs: at(0.84), endMs: safeDuration, content: "当前演示课程只在本次页面会话中存在，刷新页面后不会保留视频文件。" },
  ];
  return {
    id: `upload-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
    title,
    source: "本地上传 · 前端演示",
    year: String(new Date().getFullYear()),
    duration: formatTimestamp(safeDuration),
    durationMs: safeDuration,
    timeRange: `${formatTimestamp(segments[0].startMs)} – ${formatTimestamp(segments[2].endMs)}`,
    timestamp: formatTimestamp(segments[0].startMs),
    timestampMs: segments[0].startMs,
    preview: "本地视频已加入当前会话。转写、摘要与问答为明确标注的演示数据。",
    visual: "science",
    videoUrl,
    isDemoUpload: true,
    transcript: segments,
    summary: {
      overview: `“${title}”已进入前端演示阅读流程。当前页面未分析实际音视频内容，以下要点仅说明可体验的产品能力。`,
      keyPoints: [
        "视频直接从本地对象 URL 播放，不会发送到服务器。",
        "转写、摘要章节和问答引用可以联动同一播放时间轴。",
        "课程仅保留在当前会话，刷新页面后恢复内置演示数据。",
      ],
      chapters: [
        { id: `${title}-chapter-1`, title: "本地视频播放", description: "体验本地文件播放和进度控制。", startMs: at(0.05) },
        { id: `${title}-chapter-2`, title: "转写时间联动", description: "查看演示转写随播放进度高亮。", startMs: at(0.2) },
        { id: `${title}-chapter-3`, title: "摘要与问答引用", description: "从摘要或问答跳转到播放器。", startMs: at(0.42) },
      ],
    },
    qaRules: [
      { keywords: ["演示", "模式"], answer: "当前为纯前端演示：视频只在本机播放，转写、摘要和回答不会分析文件的真实内容。", citationMs: at(0.05) },
      { keywords: ["转写", "字幕"], answer: "这里展示的是示例转写，用于验证时间戳与播放器联动；真实转写需要接入后端 ASR 服务。", citationMs: at(0.2) },
      { keywords: ["摘要", "要点"], answer: "摘要页当前展示产品结构，包括概览、关键要点和章节导航，内容已明确标注为演示数据。", citationMs: at(0.42) },
    ],
  };
}

export function UploadPage({ onComplete }: UploadPageProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const timersRef = useRef<Set<number>>(new Set());
  const runIdRef = useRef(0);
  const durationPromiseRef = useRef<Promise<number>>(Promise.resolve(fallbackDurationMs));
  const [isDragging, setIsDragging] = useState(false);
  const [selectedFile, setSelectedFile] = useState<File | null>(null);
  const [durationMs, setDurationMs] = useState(fallbackDurationMs);
  const [steps, setSteps] = useState<ProcessingStep[]>(processingSteps);
  const [message, setMessage] = useState("支持 MP4、WebM、MOV、MKV；单文件不超过 500 MB。文件不会离开浏览器。");
  const [isProcessing, setIsProcessing] = useState(false);

  const clearTimers = () => {
    timersRef.current.forEach((timer) => window.clearTimeout(timer));
    timersRef.current.clear();
  };

  useEffect(() => () => {
    runIdRef.current += 1;
    clearTimers();
  }, []);

  const resetSteps = (file?: File) => processingSteps.map((step, index) => ({
    ...step,
    description: index === 0 && file ? `${file.name} · ${formatFileSize(file.size)}` : step.description,
    state: "pending" as const,
    detail: "等待中",
  }));

  const selectFile = (file?: File) => {
    runIdRef.current += 1;
    clearTimers();
    setIsProcessing(false);
    if (!file) return;
    if (!hasAcceptedFormat(file)) {
      setSelectedFile(null);
      setSteps(resetSteps());
      setMessage("请选择 MP4、WebM、MOV 或 MKV 格式的视频文件。");
      return;
    }
    if (file.size > maxFileSize) {
      setSelectedFile(null);
      setSteps(resetSteps());
      setMessage("当前文件超过 500 MB 的演示限制，请选择更小的视频。");
      return;
    }
    const selectionId = runIdRef.current;
    setSelectedFile(file);
    setDurationMs(fallbackDurationMs);
    setMessage(`已选择 ${file.name}（${formatFileSize(file.size)}），可以开始演示解析。`);
    setSteps(resetSteps(file));
    durationPromiseRef.current = readVideoDuration(file);
    void durationPromiseRef.current.then((value) => {
      if (runIdRef.current === selectionId) setDurationMs(value);
    });
  };

  const waitForStage = () => new Promise<void>((resolve) => {
    const timer = window.setTimeout(() => {
      timersRef.current.delete(timer);
      resolve();
    }, 450);
    timersRef.current.add(timer);
  });

  const beginProcessing = async () => {
    if (!selectedFile || isProcessing) return;
    clearTimers();
    const runId = ++runIdRef.current;
    setIsProcessing(true);
    setMessage("正在本地模拟处理流程，视频不会上传…");

    for (let index = 0; index < processingSteps.length; index += 1) {
      setSteps((current) => current.map((step, stepIndex) => ({
        ...step,
        state: stepIndex < index ? "complete" : stepIndex === index ? "working" : "pending",
        detail: stepIndex < index ? "已完成" : stepIndex === index ? "进行中" : "等待中",
      })));
      await waitForStage();
      if (runIdRef.current !== runId) return;
    }

    setSteps((current) => current.map((step) => ({ ...step, state: "complete", detail: "已完成" })));
    setMessage("演示处理完成，正在打开课程阅读页。");
    setIsProcessing(false);
    try {
      const resolvedDurationMs = await durationPromiseRef.current;
      if (runIdRef.current !== runId) return;
      const videoUrl = URL.createObjectURL(selectedFile);
      onComplete(createUploadedLecture(selectedFile, resolvedDurationMs, videoUrl));
    } catch {
      setMessage("浏览器无法读取该本地视频，请重新选择文件。");
    }
  };

  const handleInput = (event: ChangeEvent<HTMLInputElement>) => selectFile(event.target.files?.[0]);
  const handleDrop = (event: DragEvent<HTMLDivElement>) => {
    event.preventDefault();
    setIsDragging(false);
    selectFile(event.dataTransfer.files[0]);
  };

  return (
    <main className="upload-page page-content">
      <div className="upload-main">
        <header className="page-heading">
          <h1>课程视频解析</h1>
          <p>上传课程视频，体验转写、检索、摘要和问答的完整前端流程。</p>
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
          <p aria-live="polite">{message}</p>
          <input ref={inputRef} type="file" accept={acceptedTypes.join(",")} onChange={handleInput} />
          <button className="outline-button" type="button" onClick={() => inputRef.current?.click()} disabled={isProcessing}>选择文件</button>
          {selectedFile && <button className="primary-button upload-submit" type="button" onClick={() => void beginProcessing()} disabled={isProcessing}>{isProcessing ? "正在处理…" : "开始演示解析"}</button>}
        </section>
        <ProcessingSteps steps={steps} />
      </div>
      <aside className="upload-aside">
        <section className="file-summary" aria-label="当前文件">
          <h2>文件</h2>
          <div className="file-preview"><span className="preview-play"><Icon name="play" /></span><span>Lecture Reader<br />本地视频</span></div>
          <strong>{selectedFile?.name || "尚未选择视频"}</strong>
          <p>{selectedFile ? `${formatFileSize(selectedFile.size)} · ${formatTimestamp(durationMs)}` : "选择文件后显示信息"}</p>
        </section>
        <section className="info-callout"><Icon name="info" /><p>这是纯前端演示模式。视频不会上传，生成的转写、摘要和问答均为演示数据。</p></section>
        <p className="backend-status backend-status--online">运行模式：前端演示</p>
      </aside>
    </main>
  );
}
