import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { lectures } from "../../data/mockLectures";
import { searchVideos } from "../../lib/api";
import type { LectureDetail } from "../../types/lecture";
import { SearchPage } from "./SearchPage";

vi.mock("../../lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("../../lib/api")>();
  return { ...actual, searchVideos: vi.fn() };
});

describe("SearchPage remote retrieval", () => {
  it("debounces backend search and opens a timestamped result", async () => {
    const lecture: LectureDetail = {
      ...lectures[0], id: "11111111-1111-4111-8111-111111111111", title: "真实课程", isRemote: true,
    };
    vi.mocked(searchVideos).mockResolvedValue([{
      video_id: lecture.id,
      original_name: "lesson.mp4",
      chunk_id: "chunk-1",
      start_ms: 12_000,
      end_ms: 18_000,
      text: "后端返回的检索片段",
      score: 0.1,
    }]);
    const onOpenLecture = vi.fn();
    render(<SearchPage lectures={[lecture]} onOpenLecture={onOpenLecture} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "后端问题" } });

    expect(await screen.findAllByText(/后端返回的检索片段/)).toHaveLength(2);
    expect(searchVideos).toHaveBeenCalledWith("后端问题", [lecture.id], expect.any(AbortSignal));
    fireEvent.click(screen.getByRole("button", { name: /从此处播放/ }));
    await waitFor(() => expect(onOpenLecture).toHaveBeenCalledWith(lecture.id, 12_000));
  });
});
