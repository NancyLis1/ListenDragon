import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { checkBackend, listVideos } from "../lib/api";
import App from "./App";

vi.mock("../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../lib/api")>();
  return { ...actual, checkBackend: vi.fn(), listVideos: vi.fn() };
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
});
