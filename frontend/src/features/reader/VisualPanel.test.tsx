import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { analyzeVisuals, getVideo, getVisualAnalysis } from "../../lib/api";
import { readSaved, saveLocal } from "../../lib/persistence";
import { VisualPanel } from "./VisualPanel";

vi.mock("../../lib/api", async (original) => ({
  ...await original<typeof import("../../lib/api")>(),
  analyzeVisuals: vi.fn(), getVideo: vi.fn(), getVisualAnalysis: vi.fn(),
}));

const empty = { status: "not_requested" as const, observations: [], error_code: null, audio_warning: null, sampling_note: "仅分析抽样画面" };

describe("VisualPanel", () => {
  beforeEach(() => {
    vi.mocked(getVisualAnalysis).mockResolvedValue(empty);
    vi.mocked(analyzeVisuals).mockResolvedValue({});
  });

  it("reprocesses an existing video and invalidates the old conversation only after completion", async () => {
    saveLocal("conversation:video", "old-conversation");
    vi.mocked(getVisualAnalysis).mockResolvedValueOnce(empty).mockResolvedValue({
      ...empty, status: "ready", version: "sequence-v3", observations: [{ timestamp_ms: 4000, text: "西瓜" }],
    });
    vi.mocked(getVideo).mockResolvedValue({ state: "READY" } as Awaited<ReturnType<typeof getVideo>>);
    const updated = vi.fn();
    render(<VisualPanel videoId="video" expanded onSeek={vi.fn()} onUpdated={updated} />);
    expect(await screen.findByText(/尚未分析画面/)).toBeTruthy();
    expect(readSaved("conversation:video")).toBe("old-conversation");
    fireEvent.click(screen.getByRole("button", { name: "开始音画分析" }));
    await waitFor(() => expect(updated).toHaveBeenCalledTimes(1));
    expect(analyzeVisuals).toHaveBeenCalledWith("video", expect.any(AbortSignal));
    expect(readSaved("conversation:video")).toBeUndefined();
    expect(screen.getByText(/画面分析完成：1 段/)).toBeTruthy();
  });

  it("shows visual failure and does not silently erase a conversation on request failure", async () => {
    saveLocal("conversation:video", "old-conversation");
    vi.mocked(getVisualAnalysis).mockResolvedValue({ ...empty, status: "failed", error_code: "LLM_UNAVAILABLE" });
    vi.mocked(analyzeVisuals).mockRejectedValue(new Error("连接失败"));
    render(<VisualPanel videoId="video" expanded onSeek={vi.fn()} onUpdated={vi.fn()} />);
    expect(await screen.findByText(/请重试后使用音画摘要和问答/)).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "开始音画分析" }));
    expect(await screen.findByRole("alert")).toHaveProperty("textContent", "连接失败");
    expect(readSaved("conversation:video")).toBe("old-conversation");
  });

  it("offers analysis from the default tab and reports busy while processing", async () => {
    const busyChanged = vi.fn();
    vi.mocked(analyzeVisuals).mockImplementation(() => new Promise(() => {}));
    const { unmount } = render(<VisualPanel videoId="video" expanded={false} onSeek={vi.fn()} onUpdated={vi.fn()} onBusyChange={busyChanged} />);
    fireEvent.click(await screen.findByRole("button", { name: "开始音画分析" }));
    await waitFor(() => expect(busyChanged).toHaveBeenLastCalledWith(true));
    expect((screen.getByRole("button", { name: "音画分析中…" }) as HTMLButtonElement).disabled).toBe(true);
    unmount();
  });
});
