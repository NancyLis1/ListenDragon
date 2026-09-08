import { useEffect, useRef, useState } from "react";

import { analyzeVisuals, getVideo, getVisualAnalysis, type ApiVisualAnalysis } from "../../lib/api";
import { saveLocal } from "../../lib/persistence";
import { formatTimestamp } from "./LectureVideo";

interface VisualPanelProps {
  videoId: string;
  expanded: boolean;
  onSeek: (timeMs: number) => void;
  onUpdated: () => void;
  onBusyChange?: (busy: boolean) => void;
}

const analysisErrors: Record<string, string> = {
  LLM_TIMEOUT: "模型响应超时，可以重试。",
  LLM_RATE_LIMITED: "模型繁忙，请稍后重试。",
  VISION_DEPENDENCY_MISSING: "请安装后端 AI 依赖后重试。",
  SCENE_DETECTION_FAILED: "请检查视频是否能正常解码后重试。",
  VISION_TOO_MANY_SCENES: "镜头数超过当前预算，请上传较短片段或调整服务端预算。",
};

export function VisualPanel({ videoId, expanded, onSeek, onUpdated, onBusyChange }: VisualPanelProps) {
  const [analysis, setAnalysis] = useState<ApiVisualAnalysis>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);
  const updated = useRef(onUpdated);
  updated.current = onUpdated;
  const busyChanged = useRef(onBusyChange);
  busyChanged.current = onBusyChange;
  useEffect(() => { busyChanged.current?.(busy); }, [busy]);

  const monitor = async (signal: AbortSignal) => {
    setBusy(true);
    while (!signal.aborted) {
      const job = await getVideo(videoId, signal);
      if (job.state === "READY" || job.state === "FAILED") {
        const result = await getVisualAnalysis(videoId, signal);
        if (signal.aborted) return;
        setAnalysis(result);
        setBusy(false);
        if (job.state === "READY") {
          // Old exchanges remain in SQLite, but must not bias answers using the new index.
          saveLocal(`conversation:${videoId}`, "");
          updated.current();
        } else setError("处理失败，请检查画面分析状态后重试。");
        return;
      }
      await new Promise((resolve) => window.setTimeout(resolve, 1000));
    }
  };

  useEffect(() => {
    const request = new AbortController();
    controller.current = request;
    void getVisualAnalysis(videoId, request.signal).then(async (result) => {
      if (request.signal.aborted) return;
      setAnalysis(result);
      if (result.status === "pending") await monitor(request.signal);
    }).catch((failure) => {
      if (!request.signal.aborted) { setError(failure instanceof Error ? failure.message : "画面状态加载失败。"); setBusy(false); }
    });
    return () => request.abort();
  }, [videoId]);

  const start = async () => {
    if (busy) return;
    controller.current?.abort();
    const request = new AbortController();
    controller.current = request;
    setBusy(true);
    setError("");
    try {
      await analyzeVisuals(videoId, request.signal);
      await monitor(request.signal);
    } catch (failure) {
      if (!request.signal.aborted) {
        setError(failure instanceof Error ? failure.message : "画面分析失败。");
        setBusy(false);
      }
    }
  };

  useEffect(() => () => controller.current?.abort(), []);

  return <section className="summary-panel" aria-label="画面分析">
    <p aria-live="polite">{busy ? "正在理解视频事件并更新索引，完成后可生成摘要和提问…" : analysis?.status === "ready" && analysis.version === "sequence-v3"
      ? `画面分析完成：${analysis.observations.length} 段事件；${analysis.audio_warning ? "语音不可用，回答依据画面。" : "回答结合画面与语音转写。"}`
      : analysis?.status === "ready" ? "此视频使用旧版画面分析。请升级分析后使用新版视频问答。"
      : analysis?.status === "failed" ? "画面分析未成功。请重试后使用音画摘要和问答；已有转写仍可查看。"
      : analysis ? "该视频尚未分析画面。点击下方开始音画分析后，再生成摘要或提问。" : "正在读取画面分析状态…"}</p>
    {analysis && (!expanded && analysis.status === "ready" && analysis.version === "sequence-v3" ? null : <>
      <p>分析会将抽样画面发送至已配置的模型；摘要和问答还会使用语音转写，可能产生费用。</p>
      <button className="outline-button" type="button" onClick={() => void start()} disabled={busy}>
        {busy ? "音画分析中…" : analysis.version === "sequence-v3" && analysis.status === "ready" ? "重新分析视频" : "开始音画分析"}
      </button>
    </>)}
    {error && <p className="reader-error" role="alert">{error}</p>}
    {expanded && <>
      <p>{analysis?.sampling_note || "画面分析采用抽样方式，可能遗漏帧之间的动作。"}</p>
      {analysis?.error_code && <p className="reader-error">画面分析失败（{analysis.error_code}）。{analysisErrors[analysis.error_code] || "请检查服务端模型与网络后重试。"}</p>}
      {analysis?.audio_warning && <p className="reader-error">语音处理未成功（{analysis.audio_warning}），不要把画面观察当作对白。</p>}
      <p>重新分析后摘要会更新，并开启空白会话；旧会话保留并标注版本变化。画面为抽样观察，转写可能有误。</p>
      <ol className="summary-chapters">{analysis?.observations.map((item, index) => <li key={`${item.timestamp_ms}:${index}`}>
        <button type="button" onClick={() => onSeek(item.timestamp_ms)} aria-label={`查看画面 ${formatTimestamp(item.timestamp_ms)}`}>
          <time>{formatTimestamp(item.timestamp_ms)}{item.end_ms ? `–${formatTimestamp(item.end_ms)}` : ""}</time><span className="chapter-copy">{item.text}</span>
        </button>
      </li>)}</ol>
    </>}
  </section>;
}
