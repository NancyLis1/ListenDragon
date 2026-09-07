import { useEffect, useRef, useState } from "react";

import { getSummary, getTranscript, type ApiSummary } from "../../lib/api";
import type { LectureDetail, SeekRequest } from "../../types/lecture";
import { ChatPanel } from "./ChatPanel";
import { LectureVideo } from "./LectureVideo";
import { SummaryPanel } from "./SummaryPanel";
import { Transcript } from "./Transcript";

interface ReaderPageProps {
  lecture: LectureDetail;
  initialTimeMs?: number;
}

export function ReaderPage({ lecture, initialTimeMs = 0 }: ReaderPageProps) {
  const [currentTimeMs, setCurrentTimeMs] = useState(initialTimeMs);
  const [seekRequest, setSeekRequest] = useState<SeekRequest>({ timeMs: initialTimeMs, token: 0 });
  const [activeTab, setActiveTab] = useState<"transcript" | "summary">("transcript");
  const [segments, setSegments] = useState(lecture.transcript);
  const [transcriptError, setTranscriptError] = useState("");
  const [transcriptLoading, setTranscriptLoading] = useState(lecture.isRemote === true);
  const [generatedSummary, setGeneratedSummary] = useState<ApiSummary | null>(null);
  const [summaryLoading, setSummaryLoading] = useState(false);
  const [summaryError, setSummaryError] = useState("");
  const summaryController = useRef<AbortController | null>(null);

  useEffect(() => {
    setCurrentTimeMs(initialTimeMs);
    setSeekRequest({ timeMs: initialTimeMs, token: 0 });
    setActiveTab("transcript");
    setSegments(lecture.transcript);
    setTranscriptError("");
    setGeneratedSummary(null);
    setSummaryError("");
    if (!lecture.isRemote) {
      setTranscriptLoading(false);
      return;
    }
    const controller = new AbortController();
    setTranscriptLoading(true);
    void getTranscript(lecture.id, controller.signal)
      .then((items) => setSegments(items.map((item) => ({
        id: `${lecture.id}-${item.seq}`,
        startMs: item.start_ms,
        endMs: item.end_ms,
        content: item.text,
      }))))
      .catch((error) => {
        if (!controller.signal.aborted) setTranscriptError(error instanceof Error ? error.message : "转写加载失败。");
      })
      .finally(() => { if (!controller.signal.aborted) setTranscriptLoading(false); });
    return () => controller.abort();
  }, [lecture.id, initialTimeMs]);

  useEffect(() => () => summaryController.current?.abort(), []);

  const seekTo = (timeMs: number) => {
    const boundedTime = Math.max(0, Math.min(timeMs, lecture.durationMs));
    setCurrentTimeMs(boundedTime);
    setSeekRequest((current) => ({ timeMs: boundedTime, token: current.token + 1 }));
  };

  const openChapter = (timeMs: number) => {
    setActiveTab("transcript");
    seekTo(timeMs);
  };

  const openSummary = () => {
    setActiveTab("summary");
    if (!lecture.isRemote || generatedSummary || summaryLoading) return;
    summaryController.current?.abort();
    const controller = new AbortController();
    summaryController.current = controller;
    setSummaryLoading(true);
    setSummaryError("");
    void getSummary(lecture.id, controller.signal)
      .then(setGeneratedSummary)
      .catch((error) => {
        if (!controller.signal.aborted) setSummaryError(error instanceof Error ? error.message : "摘要生成失败。");
      })
      .finally(() => { if (!controller.signal.aborted) setSummaryLoading(false); });
  };

  return (
    <main className="reader-page page-content">
      <section className="reader-main">
        <header className="reader-heading">
          <div>
            <h1>{lecture.title}</h1>
            <p>{lecture.source} · {lecture.year}</p>
          </div>
          {!lecture.isRemote && <span className="demo-badge">体验样例</span>}
        </header>
        {!lecture.isRemote && (
          <p className="demo-notice">当前为离线体验样例；转写、摘要与问答并非来自你上传的视频。</p>
        )}
        <LectureVideo lecture={lecture} seekRequest={seekRequest} onTimeChange={setCurrentTimeMs} />
        <div className="reader-tabs" role="tablist" aria-label="课程内容">
          <button type="button" role="tab" aria-selected={activeTab === "transcript"} onClick={() => setActiveTab("transcript")}>转写</button>
          <button type="button" role="tab" aria-selected={activeTab === "summary"} onClick={openSummary}>摘要</button>
        </div>
        {activeTab === "transcript" ? (
          transcriptLoading ? <p>正在加载转写…</p> : transcriptError ? <p className="reader-error">{transcriptError}</p> :
          <Transcript key={lecture.id} segments={segments} currentTimeMs={currentTimeMs} onSeek={seekTo} />
        ) : (
          <SummaryPanel summary={lecture.summary} generated={generatedSummary} loading={summaryLoading} error={summaryError} onChapterSelect={openChapter} />
        )}
      </section>
      <ChatPanel key={lecture.id} lecture={lecture} onSeek={seekTo} />
    </main>
  );
}
