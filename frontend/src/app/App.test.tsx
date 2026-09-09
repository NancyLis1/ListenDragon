import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { checkBackend, getTranscript, listVideos } from "../lib/api";
import { saveLocal } from "../lib/persistence";
import App from "./App";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, checkBackend: vi.fn(), listVideos: vi.fn(), getTranscript: vi.fn(), getUploadLimits: vi.fn().mockResolvedValue({ max_upload_bytes: 500 * 1024 * 1024, max_video_minutes: 60 }), getVisualAnalysis: vi.fn().mockResolvedValue({ status: "not_requested", observations: [] }) };
});

describe("App persisted library", () => {
  beforeEach(() => {
    window.location.hash = "#upload";
    vi.mocked(checkBackend).mockResolvedValue("online");
    vi.mocked(listVideos).mockResolvedValue([{
      video_id: "11111111-1111-4111-8111-111111111111",
      original_name: "persisted-lesson.mp4",
      mime: "video/mp4",
      size_bytes: 10,
      duration_ms: 60_000,
      created_at: "2026-09-08T00:00:00Z",
      state: "READY",
      progress: 100,
      error_code: null,
    }]);
  });

  it("restores ready backend videos instead of mixing sample courses", async () => {
    render(<App />);
    expect(await screen.findByText("后端状态：已连接")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: /检索内容/ }));
    window.dispatchEvent(new HashChangeEvent("hashchange"));
    fireEvent.change(await screen.findByRole("textbox"), { target: { value: "" } });

    expect(await screen.findAllByText("persisted-lesson")).toHaveLength(2);
    expect(screen.queryByText(/Transformer 内部机制/)).toBeNull();
  });

  it("restores the selected older video instead of opening the newest upload", async () => {
    const existing = await listVideos();
    vi.mocked(listVideos).mockResolvedValue([
      { ...existing[0], video_id: "22222222-2222-4222-8222-222222222222", original_name: "newest.mp4" },
      existing[0],
    ]);
    vi.mocked(getTranscript).mockResolvedValue([]);
    saveLocal("active-video", existing[0].video_id);
    window.location.hash = "#reader";
    render(<App />);
    expect(await screen.findByRole("heading", { name: "persisted-lesson" })).toBeTruthy();
    expect(screen.queryByRole("heading", { name: "newest" })).toBeNull();
  });
});
