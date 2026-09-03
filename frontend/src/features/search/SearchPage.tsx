import { useMemo, useState } from "react";

import { Icon } from "../../components/Icon";
import { VideoArtwork } from "../../components/VideoArtwork";
import { lectures } from "../../data/mockLectures";
import type { Lecture } from "../../types/lecture";
import { SearchResultCard } from "./SearchResultCard";

interface SearchPageProps {
  onOpenLecture: () => void;
}

const initialQuery = "教授在哪里解释了 RoPE 和正弦位置编码的区别？";

export function SearchPage({ onOpenLecture }: SearchPageProps) {
  const [query, setQuery] = useState(initialQuery);
  const [selectedLecture, setSelectedLecture] = useState<Lecture>(lectures[0]);
  const matchingLectures = useMemo(() => {
    const normalized = query.trim().toLowerCase();
    if (!normalized) return lectures;
    if (["rope", "位置编码", "transformer"].some((keyword) => normalized.includes(keyword))) return lectures;
    const terms = normalized.split(/[\s，？?、]+/).filter((term) => term.length > 1);
    const matches = lectures.filter((lecture) => terms.some((term) => `${lecture.title} ${lecture.source} ${lecture.preview}`.toLowerCase().includes(term)));
    return matches.length ? matches : lectures;
  }, [query]);

  return (
    <main className="search-page page-content">
      <section className="search-results-panel" aria-labelledby="search-title">
        <label className="search-input" id="search-title">
          <Icon name="search" />
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="在课程转写、幻灯片和摘要中搜索" />
          {query && <button type="button" onClick={() => setQuery("")} aria-label="清除搜索"><Icon name="close" /></button>}
        </label>
        <p className="result-count">{matchingLectures.length} 条结果</p>
        <div className="result-list">
          {matchingLectures.map((lecture) => <SearchResultCard key={lecture.id} lecture={lecture} selected={selectedLecture.id === lecture.id} onSelect={setSelectedLecture} />)}
        </div>
        <p className="result-footer">显示 {matchingLectures.length} 条相关内容</p>
      </section>
      <aside className="search-preview" aria-live="polite">
        <VideoArtwork visual={selectedLecture.visual} className="preview-artwork" />
        <h1>{selectedLecture.title}</h1>
        <p>{selectedLecture.source} · {selectedLecture.year}</p>
        <strong>{selectedLecture.timeRange}</strong>
        <p className="preview-text">{selectedLecture.preview}</p>
        <button className="primary-button play-from-here" type="button" onClick={onOpenLecture}><Icon name="play" />从此处播放</button>
      </aside>
    </main>
  );
}
