import type { LectureSummary } from "../../types/lecture";
import { formatTimestamp } from "./LectureVideo";

interface SummaryPanelProps {
  summary: LectureSummary;
  onChapterSelect: (timeMs: number) => void;
}

export function SummaryPanel({ summary, onChapterSelect }: SummaryPanelProps) {
  return (
    <section className="summary-panel" aria-label="视频摘要">
      <div className="summary-overview">
        <span>内容概览</span>
        <p>{summary.overview}</p>
      </div>
      <div className="summary-section">
        <h2>关键要点</h2>
        <ul>
          {summary.keyPoints.map((point) => <li key={point}>{point}</li>)}
        </ul>
      </div>
      <div className="summary-section">
        <h2>章节导航</h2>
        <ol className="summary-chapters">
          {summary.chapters.map((chapter, index) => (
            <li key={chapter.id}>
              <button type="button" onClick={() => onChapterSelect(chapter.startMs)} aria-label={`播放章节 ${chapter.title}`}>
                <span className="chapter-index">{String(index + 1).padStart(2, "0")}</span>
                <span className="chapter-copy"><strong>{chapter.title}</strong><small>{chapter.description}</small></span>
                <time>{formatTimestamp(chapter.startMs)}</time>
              </button>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
