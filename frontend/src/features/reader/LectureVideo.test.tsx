import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { lectures } from "../../data/mockLectures";
import { LectureVideo } from "./LectureVideo";

const lecture = { ...lectures[0], durationMs: 60_000, videoUrl: "/sample.mp4" };
const onTimeChange = vi.fn();

describe("timestamp playback", () => {
  beforeEach(() => {
    vi.spyOn(HTMLMediaElement.prototype, "play").mockImplementation(function (this: HTMLMediaElement) {
      this.dispatchEvent(new Event("play"));
      return Promise.resolve();
    });
  });

  afterEach(() => vi.restoreAllMocks());

  it("does not autoplay on initial load, then seeks and plays on each timestamp click", () => {
    const { container, rerender } = render(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 2000, token: 0 }} onTimeChange={onTimeChange} />);
    const video = container.querySelector("video")!;
    Object.defineProperty(video, "readyState", { configurable: true, value: 1 });
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(2);
    expect(video.play).not.toHaveBeenCalled();

    rerender(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 4500, token: 1 }} onTimeChange={onTimeChange} />);
    expect(video.currentTime).toBe(4.5);
    expect(video.play).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "暂停" })).toBeTruthy();

    fireEvent.pause(video);
    rerender(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 4500, token: 2 }} onTimeChange={onTimeChange} />);
    expect(video.play).toHaveBeenCalledTimes(2);
    expect(screen.getByRole("button", { name: "暂停" })).toBeTruthy();
  });

  it("keeps the latest timestamp when metadata arrives after multiple clicks", () => {
    const { container, rerender } = render(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 0, token: 0 }} onTimeChange={onTimeChange} />);
    const video = container.querySelector("video")!;
    rerender(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 4000, token: 1 }} onTimeChange={onTimeChange} />);
    rerender(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 8000, token: 2 }} onTimeChange={onTimeChange} />);
    expect(video.play).toHaveBeenCalledTimes(2);
    fireEvent.loadedMetadata(video);
    expect(video.currentTime).toBe(8);
  });

  it("explains blocked autoplay and keeps manual playback available", async () => {
    vi.mocked(HTMLMediaElement.prototype.play).mockRejectedValueOnce(new DOMException("blocked", "NotAllowedError"));
    render(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 4000, token: 1 }} onTimeChange={onTimeChange} />);
    expect((await screen.findByRole("alert")).textContent).toContain("浏览器阻止了自动播放");
    fireEvent.click(screen.getByRole("button", { name: "播放" }));
    expect(await screen.findByRole("button", { name: "暂停" })).toBeTruthy();
    expect(screen.queryByRole("alert")).toBeNull();
  });

  it("ignores a stale play failure after a newer timestamp succeeds", async () => {
    let rejectOld!: (error: Error) => void;
    vi.mocked(HTMLMediaElement.prototype.play).mockImplementationOnce(() => new Promise<void>((_, reject) => { rejectOld = reject; }));
    const { rerender } = render(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 4000, token: 1 }} onTimeChange={onTimeChange} />);
    rerender(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 8000, token: 2 }} onTimeChange={onTimeChange} />);
    await act(async () => { rejectOld(new Error("interrupted")); });
    expect(screen.queryByRole("alert")).toBeNull();
    expect(screen.getByRole("button", { name: "暂停" })).toBeTruthy();
  });

  it("does not start playback when dragging the progress slider while paused", () => {
    const { container } = render(<LectureVideo lecture={lecture} seekRequest={{ timeMs: 0, token: 0 }} onTimeChange={onTimeChange} />);
    fireEvent.change(screen.getByRole("slider", { name: "播放进度" }), { target: { value: "12" } });
    expect(container.querySelector("video")!.currentTime).toBe(12);
    expect(HTMLMediaElement.prototype.play).not.toHaveBeenCalled();
  });
});
