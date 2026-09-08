import type { ApiSummary } from "../../lib/api";
import type { LectureSummary } from "../../types/lecture";
import { formatTimestamp } from "./LectureVideo";

interface SummaryPanelProps {
  summary: LectureSummary;
  generated?: ApiSummary | null;
  loading?: boolean;
  error?: string;
  onChapterSelect: (timeMs: number) => void;
}

function SummaryContent({ content }: { content: string }) {
  return <div className="generated-summary">{content.split(/\n+/).filter(Boolean).map((line, index) => {
    const heading = line.match(/^#{1,3}\s+(.+)$/);
    return heading
      ? <h2 key={`${heading[1]}-${index}`}>{heading[1]}</h2>
      : <p key={`${line.slice(0, 20)}-${index}`}>{line}</p>;
  })}</div>;
}

export function SummaryPanel({ summary, generated, loading, error, onChapterSelect }: SummaryPanelProps) {
  if (loading) return <section className="summary-panel" aria-label="视频摘要"><p>正在生成有依据的摘要…</p></section>;
  if (error) return <section className="summary-panel" aria-label="视频摘要"><p className="reader-error">{error}</p></section>;
  if (generated) {
    return (
      <section className="summary-panel" aria-label="视频摘要">
        <SummaryContent content={generated.summary} />
        <div className="summary-section">
          <h2>引用片段</h2>
          <ol className="summary-chapters">
            {generated.evidence.map((item, index) => (
              <li key={item.chunk_id}>
                <button type="button" onClick={() => onChapterSelect(item.start_ms)} aria-label={`播放引用 ${item.timestamp}`}>
                  <span className="chapter-index">{String(index + 1).padStart(2, "0")}</span>
                  <span className="chapter-copy"><strong>{item.source_type === "visual" ? "画面观察" : "语音转写"} {item.timestamp}</strong><small>{item.text}</small></span>
                  <time>{formatTimestamp(item.start_ms)}</time>
                </button>
              </li>
            ))}
          </ol>
        </div>
      </section>
    );
  }
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
