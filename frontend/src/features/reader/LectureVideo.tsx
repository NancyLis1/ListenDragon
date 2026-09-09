import { useEffect, useRef, useState, type ChangeEvent } from "react";

import { Icon } from "../../components/Icon";
import { VideoArtwork } from "../../components/VideoArtwork";
import type { LectureDetail, SeekRequest } from "../../types/lecture";

interface LectureVideoProps {
  lecture: LectureDetail;
  seekRequest: SeekRequest;
  onTimeChange: (timeMs: number) => void;
}

export function formatTimestamp(timeMs: number) {
  const totalSeconds = Math.max(0, Math.floor(timeMs / 1000));
  const hours = Math.floor(totalSeconds / 3600);
  const minutes = Math.floor((totalSeconds % 3600) / 60);
  const seconds = totalSeconds % 60;
  return hours > 0
    ? `${hours}:${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`
    : `${minutes}:${String(seconds).padStart(2, "0")}`;
}

export function LectureVideo({ lecture, seekRequest, onTimeChange }: LectureVideoProps) {
  const playerRef = useRef<HTMLElement>(null);
  const videoRef = useRef<HTMLVideoElement>(null);
  const [isPlaying, setIsPlaying] = useState(false);
  const [currentTimeMs, setCurrentTimeMs] = useState(seekRequest.timeMs);
  const [playbackRate, setPlaybackRate] = useState(1);
  const [playbackError, setPlaybackError] = useState("");

  const updateTime = (timeMs: number) => {
    const boundedTime = Math.max(0, Math.min(timeMs, lecture.durationMs));
    setCurrentTimeMs(boundedTime);
    onTimeChange(boundedTime);
  };

  useEffect(() => {
    const timeMs = Math.max(0, Math.min(seekRequest.timeMs, lecture.durationMs));
    setCurrentTimeMs(timeMs);
    onTimeChange(timeMs);
    const video = videoRef.current;
    // Token 0 initializes the reader; only an explicit timestamp click starts playback.
    const shouldPlay = seekRequest.token > 0;
    if (!video) {
      setIsPlaying(shouldPlay);
      return;
    }

    let cancelled = false;
    const seek = () => { video.currentTime = timeMs / 1000; };
    if (video.readyState >= 1) seek();
    else video.addEventListener("loadedmetadata", seek, { once: true });

    if (shouldPlay) {
      setPlaybackError("");
      // Request playback immediately; a late metadata event applies the pending seek.
      void video.play().catch((error: unknown) => {
        if (cancelled) return;
        setIsPlaying(false);
        setPlaybackError(error instanceof DOMException && error.name === "NotAllowedError"
          ? "浏览器阻止了自动播放，请点击播放按钮继续。"
          : "视频自动播放失败，请检查网络或视频格式后点击播放重试。");
      });
    }
    return () => {
      cancelled = true;
      video.removeEventListener("loadedmetadata", seek);
    };
  }, [seekRequest.token, seekRequest.timeMs, lecture.id, lecture.videoUrl, lecture.durationMs, onTimeChange]);

  useEffect(() => {
    if (lecture.videoUrl || !isPlaying) return;
    const timer = window.setInterval(() => {
      setCurrentTimeMs((current) => {
        const next = Math.min(current + 1000, lecture.durationMs);
        onTimeChange(next);
        if (next >= lecture.durationMs) setIsPlaying(false);
        return next;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [isPlaying, lecture.durationMs, lecture.videoUrl, onTimeChange]);

  const togglePlayback = async () => {
    if (!videoRef.current) {
      setIsPlaying((value) => !value);
      return;
    }
    if (videoRef.current.paused) {
      try {
        setPlaybackError("");
        await videoRef.current.play();
        setIsPlaying(true);
      } catch {
        setIsPlaying(false);
        setPlaybackError("视频播放失败，请检查网络、源文件或浏览器格式支持后重试。");
      }
    } else {
      videoRef.current.pause();
      setIsPlaying(false);
    }
  };

  const changeProgress = (event: ChangeEvent<HTMLInputElement>) => {
    const next = Number(event.target.value) * 1000;
    updateTime(next);
    if (videoRef.current) videoRef.current.currentTime = next / 1000;
  };

  const cyclePlaybackRate = () => {
    const rates = [1, 1.25, 1.5, 2];
    const next = rates[(rates.indexOf(playbackRate) + 1) % rates.length];
    setPlaybackRate(next);
    if (videoRef.current) videoRef.current.playbackRate = next;
  };

  const enterFullscreen = () => {
    void playerRef.current?.requestFullscreen?.();
  };

  const progress = lecture.durationMs ? Math.min(100, (currentTimeMs / lecture.durationMs) * 100) : 0;

  return (
    <section ref={playerRef} className="lecture-player" aria-label="课程播放器">
      {lecture.videoUrl ? (
        <video
          ref={videoRef}
          className="lecture-video"
          src={lecture.videoUrl}
          onError={() => setPlaybackError("视频加载失败，请检查网络及源文件是否可用后刷新重试。")}
          onTimeUpdate={(event) => updateTime(event.currentTarget.currentTime * 1000)}
          onPlay={() => setIsPlaying(true)}
          onPause={() => setIsPlaying(false)}
          onEnded={() => setIsPlaying(false)}
          playsInline
        />
      ) : (
        <VideoArtwork visual={lecture.visual} className="lecture-artwork" />
      )}
      {playbackError && <p className="reader-error" role="alert">{playbackError}</p>}
      <div className="player-controls">
        <button type="button" onClick={() => void togglePlayback()} aria-label={isPlaying ? "暂停" : "播放"}>
          <Icon name={isPlaying ? "pause" : "play"} />
        </button>
        <span>{formatTimestamp(currentTimeMs)} / {formatTimestamp(lecture.durationMs)}</span>
        <label className="progress-control" aria-label="播放进度">
          <input
            type="range"
            min="0"
            max={Math.max(1, Math.round(lecture.durationMs / 1000))}
            value={Math.round(currentTimeMs / 1000)}
            onChange={changeProgress}
            style={{ background: `linear-gradient(90deg, #3478f2 0 ${progress}%, #8a9298 ${progress}% 100%)` }}
          />
        </label>
        <button type="button" className="playback-rate" onClick={cyclePlaybackRate} aria-label="切换播放速度">{playbackRate}×</button>
        <button type="button" aria-label="字幕不可用" disabled title="暂不提供字幕轨道"><Icon name="captions" /></button>
        <button type="button" onClick={enterFullscreen} aria-label="全屏"><Icon name="expand" /></button>
      </div>
    </section>
  );
}
