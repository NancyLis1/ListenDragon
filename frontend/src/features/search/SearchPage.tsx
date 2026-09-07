import { useMemo, useState } from "react";

import { Icon } from "../../components/Icon";
import { VideoArtwork } from "../../components/VideoArtwork";
import type { LectureDetail, LectureSearchResult } from "../../types/lecture";
import { formatTimestamp } from "../reader/LectureVideo";
import { SearchResultCard } from "./SearchResultCard";

interface SearchPageProps {
  lectures: LectureDetail[];
  onOpenLecture: (lectureId: string, timeMs: number) => void;
}

const initialQuery = "教授在哪里解释了 RoPE 和正弦位置编码的区别？";

const normalizeTerms = (query: string) => query.trim().toLowerCase().split(/[\s，。！？?、：:；;（）()]+/).filter((term) => term.length > 1);
const includesTerm = (value: string, terms: string[]) => terms.some((term) => value.toLowerCase().includes(term));

export function findLectureMatches(lectures: LectureDetail[], query: string): LectureSearchResult[] {
  const terms = normalizeTerms(query);
  if (terms.length === 0) {
    return lectures.map((lecture) => ({ lecture, timestampMs: lecture.timestampMs, timeRange: lecture.timeRange, preview: lecture.preview }));
  }

  return lectures.flatMap((lecture) => {
    const transcriptMatch = lecture.transcript.find((segment) => includesTerm(segment.content, terms));
    if (transcriptMatch) {
      return [{
        lecture,
        timestampMs: transcriptMatch.startMs,
        timeRange: `${formatTimestamp(transcriptMatch.startMs)} – ${formatTimestamp(transcriptMatch.endMs)}`,
        preview: transcriptMatch.content,
      }];
    }
    const chapterMatch = lecture.summary.chapters.find((chapter) => includesTerm(`${chapter.title} ${chapter.description}`, terms));
    if (chapterMatch) {
      return [{
        lecture,
        timestampMs: chapterMatch.startMs,
        timeRange: formatTimestamp(chapterMatch.startMs),
        preview: chapterMatch.description,
      }];
    }
    const metadata = `${lecture.title} ${lecture.source} ${lecture.year} ${lecture.preview} ${lecture.summary.overview} ${lecture.summary.keyPoints.join(" ")}`;
    return includesTerm(metadata, terms)
      ? [{ lecture, timestampMs: lecture.timestampMs, timeRange: lecture.timeRange, preview: lecture.preview }]
      : [];
  });
}

export function SearchPage({ lectures, onOpenLecture }: SearchPageProps) {
  const [query, setQuery] = useState(initialQuery);
  const [selectedId, setSelectedId] = useState(lectures[0]?.id ?? "");
  const matchingResults = useMemo(() => findLectureMatches(lectures, query), [lectures, query]);
  const selectedResult = matchingResults.find((result) => result.lecture.id === selectedId) ?? matchingResults[0];

  const updateQuery = (value: string) => {
    setQuery(value);
    setSelectedId("");
  };

  return (
    <main className="search-page page-content">
      <section className="search-results-panel" aria-labelledby="search-title">
        <label className="search-input" id="search-title">
          <Icon name="search" />
          <input value={query} onChange={(event) => updateQuery(event.target.value)} placeholder="在课程转写和摘要中搜索" />
          {query && <button type="button" onClick={() => updateQuery("")} aria-label="清除搜索"><Icon name="close" /></button>}
        </label>
        <p className="result-count">{matchingResults.length} 条结果</p>
        <div className="result-list">
          {matchingResults.map((result) => (
            <SearchResultCard
              key={result.lecture.id}
              result={result}
              selected={selectedResult?.lecture.id === result.lecture.id}
              onSelect={() => setSelectedId(result.lecture.id)}
            />
          ))}
          {matchingResults.length === 0 && (
            <div className="search-empty"><Icon name="search" /><h2>没有找到相关内容</h2><p>换一个关键词，或清空搜索查看当前会话中的课程。</p></div>
          )}
        </div>
        {matchingResults.length > 0 && <p className="result-footer">显示全部 {matchingResults.length} 条相关内容</p>}
      </section>
      <aside className={`search-preview ${selectedResult ? "" : "is-empty"}`} aria-live="polite">
        {selectedResult ? (
          <>
            <VideoArtwork visual={selectedResult.lecture.visual} className="preview-artwork" />
            <h1>{selectedResult.lecture.title}</h1>
            <p>{selectedResult.lecture.source} · {selectedResult.lecture.year}</p>
            <strong>{selectedResult.timeRange}</strong>
            <p className="preview-text">{selectedResult.preview}</p>
            <button className="primary-button play-from-here" type="button" onClick={() => onOpenLecture(selectedResult.lecture.id, selectedResult.timestampMs)}><Icon name="play" />从此处播放</button>
          </>
        ) : (
          <p className="preview-placeholder">选择或搜索课程内容后，这里会显示对应片段。</p>
        )}
      </aside>
    </main>
  );
}
