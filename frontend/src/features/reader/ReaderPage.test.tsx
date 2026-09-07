import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { lectures } from "../../data/mockLectures";
import { ReaderPage } from "./ReaderPage";

describe("ReaderPage", () => {
  it("seeks when a transcript line is selected", () => {
    render(<ReaderPage lecture={lectures[0]} initialTimeMs={0} />);

    fireEvent.click(screen.getByRole("button", { name: /32:14 正弦位置编码/ }));

    expect(screen.getByRole("slider", { name: "播放进度" }).getAttribute("value")).toBe("1934");
  });

  it("edits a session-only note", () => {
    render(<ReaderPage lecture={lectures[0]} />);
    fireEvent.click(screen.getByRole("button", { name: "编辑笔记" }));
    const note = screen.getByRole("textbox", { name: "课程笔记" }) as HTMLTextAreaElement;
    fireEvent.change(note, { target: { value: "复习相对位置编码" } });
    fireEvent.click(screen.getByRole("button", { name: "编辑笔记" }));

    expect(screen.getByText("复习相对位置编码")).toBeTruthy();
  });

  it("answers matching demo questions with a timestamp citation", () => {
    render(<ReaderPage lecture={lectures[0]} />);
    fireEvent.change(screen.getByRole("textbox", { name: "课程问题" }), { target: { value: "RoPE 如何表示相对位置？" } });
    fireEvent.click(screen.getByRole("button", { name: "发送问题" }));

    expect(screen.getByText(/按位置相关的角度旋转/)).toBeTruthy();
    expect(screen.getByRole("button", { name: "跳到 32:33" })).toBeTruthy();
  });
});
