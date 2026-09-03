import type { Lecture } from "../types/lecture";
import { Icon } from "./Icon";

interface VideoArtworkProps {
  visual: Lecture["visual"];
  duration?: string;
  className?: string;
}

export function VideoArtwork({ visual, duration, className = "" }: VideoArtworkProps) {
  return (
    <div className={`video-artwork video-artwork--${visual} ${className}`} aria-label="课程视频预览图">
      <div className="artwork-screen">
        {visual === "rope" && <><strong>RoPE vs. Sinusoidal</strong><span>PE(pos, 2i)</span><i className="diagram diagram--rope" /></>}
        {visual === "attention" && <><strong>Positional Encoding</strong><span>Transformers</span><i className="diagram diagram--attention" /></>}
        {visual === "sequence" && <><strong>Sequence Modeling</strong><span>Position matters</span><i className="diagram diagram--sequence" /></>}
        {visual === "science" && <><strong>The Scientific Method</strong><span>Observe · Question · Test</span><i className="diagram diagram--science" /></>}
      </div>
      <div className="artwork-speaker"><span className="speaker-head" /><span className="speaker-body" /></div>
      {duration && <span className="duration-badge">{duration}</span>}
      <span className="artwork-play"><Icon name="play" /></span>
    </div>
  );
}
