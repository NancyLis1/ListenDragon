import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getVideo, uploadVideo, type ApiVideo } from "../../lib/api";
import { UploadPage } from "./UploadPage";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, getVideo: vi.fn(), uploadVideo: vi.fn() };
});

const readyVideo: ApiVideo = {
  video_id: "11111111-1111-4111-8111-111111111111",
  original_name: "lesson.mp4",
  mime: "video/mp4",
  size_bytes: 5,
  duration_ms: 60_000,
  created_at: "2026-09-08T00:00:00Z",
  state: "READY",
  progress: 100,
  error_code: null,
};

describe("UploadPage", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:test") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
    vi.mocked(uploadVideo).mockResolvedValue({ video_id: readyVideo.video_id, state: "QUEUED" });
    vi.mocked(getVideo).mockResolvedValue(readyVideo);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("rejects unsupported files without starting processing", () => {
    const { container } = render(<UploadPage backendStatus="online" onComplete={() => undefined} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [new File(["notes"], "notes.txt", { type: "text/plain" })] } });

    expect(screen.getByText("请选择 MP4、WebM、MOV 或 MKV 格式的视频文件。")).toBeTruthy();
    expect(screen.queryByRole("button", { name: "开始解析" })).toBeNull();
  });

  it("rejects videos over the upload limit", () => {
    const { container } = render(<UploadPage backendStatus="online" onComplete={() => undefined} />);
    const file = new File(["video"], "large.mp4", { type: "video/mp4" });
    Object.defineProperty(file, "size", { value: 500 * 1024 * 1024 + 1 });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    expect(screen.getByText("当前文件超过 500 MB 限制，请选择更小的视频。")).toBeTruthy();
  });

  it("uploads, polls the backend and returns the ready video", async () => {
    const onComplete = vi.fn();
    const { container } = render(<UploadPage backendStatus="online" onComplete={onComplete} />);
    const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(readyVideo));
    expect(uploadVideo).toHaveBeenCalledWith(file, expect.any(AbortSignal));
    expect(getVideo).toHaveBeenCalledWith(readyVideo.video_id, expect.any(AbortSignal));
    expect(screen.getAllByText("已完成")).toHaveLength(5);
  });

  it("polls until a queued job becomes ready", async () => {
    vi.useFakeTimers();
    vi.mocked(getVideo)
      .mockResolvedValueOnce({ ...readyVideo, state: "QUEUED", progress: 0 })
      .mockResolvedValueOnce(readyVideo);
    const onComplete = vi.fn();
    const { container } = render(<UploadPage backendStatus="online" onComplete={onComplete} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["video"], "lesson.mp4", { type: "video/mp4" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));

    await act(async () => { await vi.advanceTimersByTimeAsync(1100); });
    expect(onComplete).toHaveBeenCalledWith(readyVideo);
  });

  it("does not upload while the backend is offline", () => {
    const { container } = render(<UploadPage backendStatus="offline" onComplete={() => undefined} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["video"], "lesson.mp4", { type: "video/mp4" })] },
    });
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));

    expect(screen.getByText("后端服务未连接，请启动 API 和 Worker 后重试。")).toBeTruthy();
    expect(uploadVideo).not.toHaveBeenCalled();
  });
});
