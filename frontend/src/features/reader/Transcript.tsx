import { useMemo, useState } from "react";

import { Icon } from "../../components/Icon";
import type { TranscriptSegment } from "../../types/lecture";
import { formatTimestamp } from "./LectureVideo";

interface TranscriptProps {
  segments: TranscriptSegment[];
  currentTimeMs: number;
  onSeek: (timeMs: number) => void;
}

export function Transcript({ segments, currentTimeMs, onSeek }: TranscriptProps) {
  const [noteOpen, setNoteOpen] = useState(false);
  const [note, setNote] = useState("重要：RoPE 通过旋转查询和键来表达相对位置。");
  const activeId = useMemo(() => {
    const exact = segments.find((item) => currentTimeMs >= item.startMs && currentTimeMs < item.endMs);
    if (exact) return exact.id;
    return [...segments].reverse().find((item) => currentTimeMs >= item.startMs)?.id ?? segments[0]?.id;
  }, [currentTimeMs, segments]);
  const noteIndex = Math.min(3, segments.length);

  return (
    <section className="transcript-panel" aria-label="课程转写">
      {segments.map((item, index) => (
        <div key={item.id}>
          <button
            className={`transcript-line ${activeId === item.id ? "is-active" : ""}`}
            type="button"
            onClick={() => onSeek(item.startMs)}
            aria-label={`${formatTimestamp(item.startMs)} ${item.content}`}
          >
            <time>{formatTimestamp(item.startMs)}</time><span>{item.content}</span>
          </button>
          {index + 1 === noteIndex && (
            <div className="inline-note">
              <div><strong>我的笔记</strong><button type="button" onClick={() => setNoteOpen((open) => !open)} aria-label="编辑笔记"><Icon name="note" /></button></div>
              {noteOpen ? (
                <textarea value={note} onChange={(event) => setNote(event.target.value)} aria-label="课程笔记" autoFocus />
              ) : (
                <p>{note || "还没有笔记。"}</p>
              )}
            </div>
          )}
        </div>
      ))}
    </section>
  );
}
