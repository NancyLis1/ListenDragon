import { VideoArtwork } from "../../components/VideoArtwork";
import type { Lecture } from "../../types/lecture";

interface SearchResultCardProps {
  lecture: Lecture;
  selected: boolean;
  onSelect: (lecture: Lecture) => void;
}

export function SearchResultCard({ lecture, selected, onSelect }: SearchResultCardProps) {
  return (
    <button className={`search-result ${selected ? "is-selected" : ""}`} type="button" onClick={() => onSelect(lecture)}>
      <VideoArtwork visual={lecture.visual} duration={lecture.duration} className="result-artwork" />
      <span className="result-copy">
        <strong>{lecture.title}</strong>
        <small>{lecture.source} · {lecture.year}</small>
        <em>{lecture.timeRange}</em>
        <span>… {lecture.preview}</span>
      </span>
    </button>
  );
}
