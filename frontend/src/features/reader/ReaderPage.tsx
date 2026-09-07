import { useState } from "react";

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

  const seekTo = (timeMs: number) => {
    const boundedTime = Math.max(0, Math.min(timeMs, lecture.durationMs));
    setCurrentTimeMs(boundedTime);
    setSeekRequest((current) => ({ timeMs: boundedTime, token: current.token + 1 }));
  };

  const openChapter = (timeMs: number) => {
    setActiveTab("transcript");
    seekTo(timeMs);
  };

  return (
    <main className="reader-page page-content">
      <section className="reader-main">
        <header className="reader-heading">
          <div>
            <h1>{lecture.title}</h1>
            <p>{lecture.source} · {lecture.year}</p>
          </div>
          {lecture.isDemoUpload && <span className="demo-badge">演示数据</span>}
        </header>
        {lecture.isDemoUpload && (
          <p className="demo-notice">当前视频仅在本机播放；下方转写与问答用于展示交互，并非对该文件的真实分析。</p>
        )}
        <LectureVideo lecture={lecture} seekRequest={seekRequest} onTimeChange={setCurrentTimeMs} />
        <div className="reader-tabs" role="tablist" aria-label="课程内容">
          <button type="button" role="tab" aria-selected={activeTab === "transcript"} onClick={() => setActiveTab("transcript")}>转写</button>
          <button type="button" role="tab" aria-selected={activeTab === "summary"} onClick={() => setActiveTab("summary")}>摘要</button>
        </div>
        {activeTab === "transcript" ? (
          <Transcript key={lecture.id} segments={lecture.transcript} currentTimeMs={currentTimeMs} onSeek={seekTo} />
        ) : (
          <SummaryPanel summary={lecture.summary} onChapterSelect={openChapter} />
        )}
      </section>
      <ChatPanel key={lecture.id} lecture={lecture} onSeek={seekTo} />
    </main>
  );
}
