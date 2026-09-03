import { useState } from "react";

import { Icon } from "../../components/Icon";
import { VideoArtwork } from "../../components/VideoArtwork";

export function LectureVideo() {
  const [isPlaying, setIsPlaying] = useState(false);

  return (
    <section className="lecture-player" aria-label="课程播放器">
      <VideoArtwork visual="science" className="lecture-artwork" />
      <div className="player-controls">
        <button type="button" onClick={() => setIsPlaying((value) => !value)} aria-label={isPlaying ? "暂停" : "播放"}><Icon name="play" /></button>
        <span>12:47 / 1:02:18</span>
        <label className="progress-control" aria-label="播放进度"><input type="range" min="0" max="100" value="24" readOnly /></label>
        <span>1×</span>
        <button type="button" aria-label="字幕"><Icon name="captions" /></button>
        <button type="button" aria-label="全屏"><Icon name="expand" /></button>
      </div>
    </section>
  );
}
