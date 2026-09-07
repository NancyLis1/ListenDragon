import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { UploadPage, createUploadedLecture } from "./UploadPage";

describe("UploadPage", () => {
  beforeEach(() => {
    let urlIndex = 0;
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => `blob:test-${urlIndex += 1}`) });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("rejects unsupported files without starting processing", () => {
    const { container } = render(<UploadPage onComplete={() => undefined} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["notes"], "notes.txt", { type: "text/plain" })] } });

    expect(screen.getByText("请选择 MP4、WebM、MOV 或 MKV 格式的视频文件。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "开始演示解析" })).toBeNull();
  });

  it("rejects videos over the session limit", () => {
    const { container } = render(<UploadPage onComplete={() => undefined} />);
    const file = new File(["video"], "large.mp4", { type: "video/mp4" });
    Object.defineProperty(file, "size", { value: 500 * 1024 * 1024 + 1 });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText("当前文件超过 500 MB 的演示限制，请选择更小的视频。")).toBeTruthy();
  });

  it("finishes every simulated stage and returns a session lecture", async () => {
    vi.useFakeTimers();
    const onComplete = vi.fn();
    const { container } = render(<UploadPage onComplete={onComplete} />);
    const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始演示解析" }));

    await act(async () => vi.runAllTimersAsync());

    expect(onComplete).toHaveBeenCalledTimes(1);
    expect(onComplete.mock.calls[0][0]).toMatchObject({ title: "lesson", isDemoUpload: true, durationMs: 60_000 });
    expect(URL.revokeObjectURL).toHaveBeenCalledWith("blob:test-1");
  });

  it("creates timestamped demo content from the video duration", () => {
    const lecture = createUploadedLecture(new File(["video"], "seminar.webm", { type: "video/webm" }), 100_000, "blob:seminar");

    expect(lecture.transcript[0].startMs).toBe(5_000);
    expect(lecture.summary.chapters[2].startMs).toBe(42_000);
    expect(lecture.summary.overview).toContain("未分析实际音视频内容");
  });
});
