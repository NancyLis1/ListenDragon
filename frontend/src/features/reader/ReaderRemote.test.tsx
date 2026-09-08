import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { lectures } from "../../data/mockLectures";
import { askQuestion, createConversation, getConversation, getSummary, getTranscript, getVisualAnalysis } from "../../lib/api";
import { saveLocal } from "../../lib/persistence";
import type { LectureDetail } from "../../types/lecture";
import { ReaderPage } from "./ReaderPage";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return {
    ...actual,
    askQuestion: vi.fn(),
    createConversation: vi.fn(),
    getConversation: vi.fn(),
    getSummary: vi.fn(),
    getTranscript: vi.fn(),
    getVisualAnalysis: vi.fn(),
  };
});

const videoId = "11111111-1111-4111-8111-111111111111";
const remoteLecture: LectureDetail = {
  ...lectures[0],
  id: videoId,
  title: "真实课程",
  durationMs: 20_000,
  duration: "0:20",
  videoUrl: `http://localhost:8000/api/v1/videos/${videoId}/content`,
  transcript: [],
  qaRules: [],
  isRemote: true,
};

describe("ReaderPage remote data", () => {
  beforeEach(() => {
    vi.mocked(getVisualAnalysis).mockResolvedValue({ status: "not_requested", observations: [], error_code: null, audio_warning: null, sampling_note: "仅分析抽样画面" });
    vi.mocked(getTranscript).mockResolvedValue([
      { seq: 0, start_ms: 1000, end_ms: 3000, text: "真实转写片段", language: "zh" },
    ]);
    vi.mocked(getSummary).mockResolvedValue({
      video_id: videoId,
      summary: "# 课程摘要\n\n## 要点\n真实摘要内容 [00:01-00:03]",
      evidence: [{
        chunk_id: "chunk-1", video_id: videoId, start_ms: 1000, end_ms: 3000,
        timestamp: "[00:01-00:03]", text: "真实转写片段",
      }],
      cached: false,
      generated_at: "2026-09-08T00:00:00Z",
    });
    vi.mocked(createConversation).mockResolvedValue("conversation-1");
    vi.mocked(askQuestion).mockResolvedValue({
      conversation_id: "conversation-1",
      message_id: "message-1",
      answer: "这是有依据的回答。 [00:01-00:03]",
      refused: false,
      evidence: [{
        chunk_id: "chunk-1", video_id: videoId, start_ms: 1000, end_ms: 3000,
        timestamp: "[00:01-00:03]", text: "真实转写片段",
      }],
      created_at: "2026-09-08T00:00:00Z",
    });
  });

  it("loads persisted transcript and lazily generates a cited summary", async () => {
    render(<ReaderPage lecture={remoteLecture} />);

    expect(await screen.findByText("真实转写片段")).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "摘要" }));

    expect(await screen.findByText("真实摘要内容 [00:01-00:03]")).toBeTruthy();
    expect(getSummary).toHaveBeenCalledTimes(1);
    fireEvent.click(screen.getByRole("button", { name: "播放引用 [00:01-00:03]" }));
    expect(screen.getByRole("slider", { name: "播放进度" }).getAttribute("value")).toBe("1");
  });

  it("creates one conversation and renders structured answer evidence", async () => {
    render(<ReaderPage lecture={remoteLecture} />);
    const input = screen.getByRole("textbox", { name: "课程问题" });
    fireEvent.change(input, { target: { value: "视频讲了什么？" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    expect(await screen.findByText(/这是有依据的回答/)).toBeTruthy();
    expect(createConversation).toHaveBeenCalledTimes(1);
    expect(askQuestion).toHaveBeenCalledWith("conversation-1", "视频讲了什么？");
    fireEvent.click(screen.getByRole("button", { name: "跳到 0:01" }));
    expect(screen.getByRole("slider", { name: "播放进度" }).getAttribute("value")).toBe("1");

    fireEvent.change(input, { target: { value: "再解释一下" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(askQuestion).toHaveBeenCalledTimes(2));
    expect(createConversation).toHaveBeenCalledTimes(1);
  });

  it("restores history and keeps the same conversation for a follow-up after remount", async () => {
    saveLocal(`conversation:${videoId}`, "saved-conversation");
    vi.mocked(getConversation).mockResolvedValue({
      conversation_id: "saved-conversation", video_id: videoId, created_at: "2026-09-08T00:00:00Z",
      messages: [{ message_id: "saved-message", role: "assistant", content: "已保存的回答",
        created_at: "2026-09-08T00:00:00Z", evidence: [{ chunk_id: "chunk-1", video_id: videoId,
          start_ms: 1000, end_ms: 3000, timestamp: "[00:01-00:03]", text: "真实转写片段" }] }],
    });
    render(<ReaderPage lecture={remoteLecture} />);
    expect(await screen.findByText("已保存的回答")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "跳到 0:01" }));
    expect(screen.getByRole("slider", { name: "播放进度" }).getAttribute("value")).toBe("1");
    fireEvent.change(screen.getByRole("textbox", { name: "课程问题" }), { target: { value: "继续解释" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(askQuestion).toHaveBeenCalledWith("saved-conversation", "继续解释"));
    expect(createConversation).not.toHaveBeenCalled();
  });

  it("explicitly creates a new conversation and uses it for the next question", async () => {
    render(<ReaderPage lecture={remoteLecture} />);
    fireEvent.click(screen.getByRole("button", { name: "新建会话" }));
    await waitFor(() => expect(createConversation).toHaveBeenCalledTimes(1));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "课程问题" }) as HTMLInputElement).disabled).toBe(false));
    fireEvent.change(screen.getByRole("textbox", { name: "课程问题" }), { target: { value: "第一个问题" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));
    await waitFor(() => expect(askQuestion).toHaveBeenCalledWith("conversation-1", "第一个问题"));
    expect(createConversation).toHaveBeenCalledTimes(1);
  });

  it("shows a visible error when the real video cannot load", () => {
    const { container } = render(<ReaderPage lecture={remoteLecture} />);
    fireEvent.error(container.querySelector("video")!);
    expect(screen.getByRole("alert").textContent).toContain("视频加载失败");
  });

  it("labels visual coverage and seeks to a visual observation without altering the transcript", async () => {
    vi.mocked(getVisualAnalysis).mockResolvedValue({ status: "ready", version: "sequence-v3", observations: [{ timestamp_ms: 4000, text: "可见打开的西瓜" }], error_code: null, audio_warning: null, sampling_note: "仅分析抽样画面" });
    render(<ReaderPage lecture={remoteLecture} />);
    expect(await screen.findByText(/画面分析完成：1 段事件/)).toBeTruthy();
    fireEvent.click(screen.getByRole("tab", { name: "画面" }));
    expect(screen.getByText("可见打开的西瓜")).toBeTruthy();
    fireEvent.click(screen.getByRole("button", { name: "查看画面 0:04" }));
    expect(screen.getByRole("slider", { name: "播放进度" }).getAttribute("value")).toBe("4");
    fireEvent.click(screen.getByRole("tab", { name: "转写" }));
    expect(screen.getByText("真实转写片段")).toBeTruthy();
  });

  it("preserves a saved conversation after a restore failure until explicitly replaced", async () => {
    saveLocal(`conversation:${videoId}`, "saved-conversation");
    vi.mocked(getConversation).mockRejectedValue(new Error("network unavailable"));
    render(<ReaderPage lecture={remoteLecture} />);
    expect(await screen.findByRole("alert")).toBeTruthy();
    expect((screen.getByRole("textbox", { name: "课程问题" }) as HTMLInputElement).disabled).toBe(true);
    expect(createConversation).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "新建会话" }));
    await waitFor(() => expect((screen.getByRole("textbox", { name: "课程问题" }) as HTMLInputElement).disabled).toBe(false));
    expect(createConversation).toHaveBeenCalledTimes(1);
  });
});
