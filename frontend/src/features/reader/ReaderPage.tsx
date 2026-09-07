import { useState } from "react";

import type { LectureDetail, SeekRequest } from "../../types/lecture";
import { ChatPanel } from "./ChatPanel";
import { LectureVideo } from "./LectureVideo";
import { Transcript } from "./Transcript";

interface ReaderPageProps {
  lecture: LectureDetail;
  initialTimeMs?: number;
}

export function ReaderPage({ lecture, initialTimeMs = 0 }: ReaderPageProps) {
  const [currentTimeMs, setCurrentTimeMs] = useState(initialTimeMs);
  const [seekRequest, setSeekRequest] = useState<SeekRequest>({ timeMs: initialTimeMs, token: 0 });

  const seekTo = (timeMs: number) => {
    const boundedTime = Math.max(0, Math.min(timeMs, lecture.durationMs));
    setCurrentTimeMs(boundedTime);
    setSeekRequest((current) => ({ timeMs: boundedTime, token: current.token + 1 }));
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
        <Transcript key={lecture.id} segments={lecture.transcript} currentTimeMs={currentTimeMs} onSeek={seekTo} />
      </section>
      <ChatPanel key={lecture.id} lecture={lecture} onSeek={seekTo} />
    </main>
  );
}
