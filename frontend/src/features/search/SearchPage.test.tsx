import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { lectures } from "../../data/mockLectures";
import { SearchPage, findLectureMatches } from "./SearchPage";

describe("SearchPage", () => {
  it("searches transcript and summary content", () => {
    const results = findLectureMatches(lectures, "向量范数");
    expect(results).toHaveLength(4);
    expect(results[0].preview).toContain("保持向量范数");
  });

  it("shows an empty state instead of unrelated fallback results", () => {
    render(<SearchPage lectures={lectures} onOpenLecture={() => undefined} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "完全不存在的关键词" } });

    expect(screen.getByText("没有找到相关内容")).toBeTruthy();
    expect(screen.getByText("0 条结果")).toBeTruthy();
  });

  it("opens the selected lecture at its matched timestamp", () => {
    const onOpenLecture = vi.fn();
    render(<SearchPage lectures={lectures} onOpenLecture={onOpenLecture} />);
    fireEvent.change(screen.getByRole("textbox"), { target: { value: "向量范数" } });
    fireEvent.click(screen.getByRole("button", { name: /从此处播放/ }));

    expect(onOpenLecture).toHaveBeenCalledWith("transformer-internals", 1_976_000);
  });
});
