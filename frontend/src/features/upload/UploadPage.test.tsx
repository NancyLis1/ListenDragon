import { act, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { getUploadLimits, getVideo, uploadVideo, type ApiVideo } from "../../lib/api";
import { UploadPage } from "./UploadPage";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, getUploadLimits: vi.fn(), getVideo: vi.fn(), uploadVideo: vi.fn() };
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

function metadataDuration(seconds: number) {
  vi.mocked(HTMLMediaElement.prototype.load).mockImplementation(function (this: HTMLMediaElement) {
    Object.defineProperty(this, "duration", { configurable: true, value: seconds });
    this.dispatchEvent(new Event("loadedmetadata"));
  });
}

async function finishPrecheck() {
  await act(async () => {});
}

describe("UploadPage", () => {
  beforeEach(() => {
    Object.defineProperty(URL, "createObjectURL", { configurable: true, value: vi.fn(() => "blob:test") });
    Object.defineProperty(URL, "revokeObjectURL", { configurable: true, value: vi.fn() });
    vi.spyOn(HTMLMediaElement.prototype, "load").mockImplementation(() => undefined);
    metadataDuration(60);
    vi.mocked(getUploadLimits).mockResolvedValue({ max_upload_bytes: 500 * 1024 * 1024, max_video_minutes: 60 });
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

  it("does not invent a duration or round tiny invalid files up to one megabyte", async () => {
    vi.useFakeTimers();
    vi.mocked(HTMLMediaElement.prototype.load).mockImplementation(() => undefined);
    const { container } = render(<UploadPage backendStatus="online" onComplete={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["bad"], "invalid.mp4", { type: "video/mp4" })] },
    });
    await act(async () => { await vi.advanceTimersByTimeAsync(1600); });
    expect(screen.getByText("3 B · 时长待校验")).toBeTruthy();
  });

  it("uses the server's upload size limit instead of a hardcoded limit", async () => {
    vi.mocked(getUploadLimits).mockResolvedValue({ max_upload_bytes: 2 * 1024 * 1024, max_video_minutes: 7 });
    const { container } = render(<UploadPage backendStatus="online" onComplete={() => undefined} />);
    const file = new File(["video"], "large.mp4", { type: "video/mp4" });
    Object.defineProperty(file, "size", { value: 2 * 1024 * 1024 + 1 });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });

    await finishPrecheck();
    expect(screen.getByText("单文件不超过 2 MB；视频最长 7 分钟。")).toBeTruthy();
    expect(screen.getByText("当前文件超过 2 MB 限制，请选择更小的视频。")).toBeTruthy();
    expect((screen.getByRole("button", { name: "开始解析" }) as HTMLButtonElement).disabled).toBe(true);
  });

  it("uploads, polls the backend and returns the ready video", async () => {
    const onComplete = vi.fn();
    const { container } = render(<UploadPage backendStatus="online" onComplete={onComplete} />);
    const file = new File(["video"], "lesson.mp4", { type: "video/mp4" });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    fireEvent.change(input, { target: { files: [file] } });
    await finishPrecheck();
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));

    await waitFor(() => expect(onComplete).toHaveBeenCalledWith(readyVideo));
    expect(uploadVideo).toHaveBeenCalledWith(file, expect.any(AbortSignal));
    expect(getVideo).toHaveBeenCalledWith(readyVideo.video_id, expect.any(AbortSignal));
    expect(screen.getAllByText("已完成")).toHaveLength(6);
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
    await finishPrecheck();
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

    expect((screen.getByRole("button", { name: "开始解析" }) as HTMLButtonElement).disabled).toBe(true);
    expect(screen.getByText("连接后端后可获取上传限制。")).toBeTruthy();
    expect(uploadVideo).not.toHaveBeenCalled();
  });

  it("explains an empty transcript and lets the user retry the same video", async () => {
    vi.mocked(getVideo).mockResolvedValue({ ...readyVideo, state: "FAILED", progress: 30, error_code: "ASR_EMPTY" });
    const { container } = render(<UploadPage backendStatus="online" onComplete={() => undefined} />);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    const file = new File(["video"], "silent.mp4", { type: "video/mp4" });
    fireEvent.change(input, { target: { files: [file] } });
    await finishPrecheck();
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));
    expect(await screen.findByText(/未识别到可转写的语音/)).toBeTruthy();
    expect(input.value).toBe("");
    fireEvent.change(input, { target: { files: [file] } });
    expect(screen.getByRole("button", { name: "开始解析" })).toBeTruthy();
  });

  it("blocks overlong video before upload, but accepts exactly the server limit", async () => {
    vi.mocked(getUploadLimits).mockResolvedValue({ max_upload_bytes: 1024 * 1024, max_video_minutes: 2 });
    metadataDuration(120.0001);
    const { container } = render(<UploadPage backendStatus="online" onComplete={vi.fn()} />);
    const input = container.querySelector('input[type="file"]')!;
    const file = new File(["video"], "long.mp4", { type: "video/mp4" });
    fireEvent.change(input, { target: { files: [file] } });
    await finishPrecheck();
    expect(screen.getByText("视频时长超限：最长支持 2 分钟，请截取较短片段后上传。")).toBeTruthy();
    const button = screen.getByRole("button", { name: "开始解析" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(uploadVideo).not.toHaveBeenCalled();

    metadataDuration(120);
    fireEvent.change(input, { target: { files: [file] } });
    await finishPrecheck();
    expect(button.disabled).toBe(false);
    fireEvent.click(button);
    await waitFor(() => expect(uploadVideo).toHaveBeenCalledOnce());
  });

  it("waits for metadata and ignores an older file's late metadata", async () => {
    const media: HTMLMediaElement[] = [];
    vi.mocked(HTMLMediaElement.prototype.load).mockImplementation(function (this: HTMLMediaElement) {
      media.push(this);
    });
    const { container } = render(<UploadPage backendStatus="online" onComplete={vi.fn()} />);
    const input = container.querySelector('input[type="file"]')!;
    fireEvent.change(input, { target: { files: [new File(["old"], "old.mp4", { type: "video/mp4" })] } });
    await finishPrecheck();
    const button = screen.getByRole("button", { name: "开始解析" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(uploadVideo).not.toHaveBeenCalled();
    metadataDuration(30);
    fireEvent.change(input, { target: { files: [new File(["new"], "new.mp4", { type: "video/mp4" })] } });
    await finishPrecheck();
    Object.defineProperty(media[0], "duration", { value: 4000 });
    await act(async () => { media[0].dispatchEvent(new Event("loadedmetadata")); });
    expect(button.disabled).toBe(false);
    expect(screen.queryByText(/视频时长超限/)).toBeNull();
    expect(screen.getByText("3 B · 0:30")).toBeTruthy();
  });

  it("falls back to server validation when metadata is unavailable and labels rejection correctly", async () => {
    metadataDuration(Number.NaN);
    vi.mocked(getVideo).mockResolvedValue({ ...readyVideo, state: "FAILED", progress: 10, error_code: "VIDEO_TOO_LONG" });
    const { container } = render(<UploadPage backendStatus="online" onComplete={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["video"], "unknown.mp4", { type: "video/mp4" })] },
    });
    await finishPrecheck();
    expect(screen.getByText("未能读取视频时长，上传后由服务端校验。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "开始解析" }));
    expect(await screen.findByText(/视频时长超限：最长支持 60 分钟.*VIDEO_TOO_LONG/)).toBeTruthy();
    expect(screen.getByText("视频时长校验").closest("li")?.textContent).toContain("未通过");
    expect(screen.queryByText("提取音频")).toBeNull();
    expect(screen.getAllByText("已完成")).toHaveLength(1);
  });

  it("does not upload without server limits and allows retrying their fetch", async () => {
    vi.mocked(getUploadLimits).mockRejectedValueOnce(new Error("offline"));
    const { container } = render(<UploadPage backendStatus="online" onComplete={vi.fn()} />);
    fireEvent.change(container.querySelector('input[type="file"]')!, {
      target: { files: [new File(["video"], "lesson.mp4", { type: "video/mp4" })] },
    });
    await finishPrecheck();
    const button = screen.getByRole("button", { name: "开始解析" }) as HTMLButtonElement;
    expect(button.disabled).toBe(true);
    expect(screen.getByText("无法获取上传限制，请确认后端已更新后重试。")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "重试获取限制" }));
    await finishPrecheck();
    expect(button.disabled).toBe(false);
    expect(uploadVideo).not.toHaveBeenCalled();
  });
});
