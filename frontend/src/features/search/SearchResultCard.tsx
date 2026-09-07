import { VideoArtwork } from "../../components/VideoArtwork";
import type { LectureSearchResult } from "../../types/lecture";

interface SearchResultCardProps {
  result: LectureSearchResult;
  selected: boolean;
  onSelect: () => void;
}

export function SearchResultCard({ result, selected, onSelect }: SearchResultCardProps) {
  const { lecture } = result;
  return (
    <button className={`search-result ${selected ? "is-selected" : ""}`} type="button" onClick={onSelect}>
      <VideoArtwork visual={lecture.visual} duration={lecture.duration} className="result-artwork" />
      <span className="result-copy">
        <strong>{lecture.title}</strong>
        <small>{lecture.source} · {lecture.year}</small>
        <em>{result.timeRange}</em>
        <span>… {result.preview}</span>
      </span>
    </button>
  );
}
