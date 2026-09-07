import { useState, type FormEvent } from "react";

import { Icon } from "../../components/Icon";
import { initialChat } from "../../data/mockLectures";
import type { ChatMessage, LectureDetail } from "../../types/lecture";
import { formatTimestamp } from "./LectureVideo";

interface ChatPanelProps {
  lecture: LectureDetail;
  onSeek: (timeMs: number) => void;
}

function getCurrentTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());
}

export function findDemoAnswer(lecture: LectureDetail, question: string) {
  const normalized = question.trim().toLowerCase();
  return lecture.qaRules.find((rule) => rule.keywords.some((keyword) => normalized.includes(keyword.toLowerCase())));
}

export function ChatPanel({ lecture, onSeek }: ChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessage[]>(lecture.isDemoUpload ? [] : initialChat);
  const [question, setQuestion] = useState("");

  const submitQuestion = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content) return;
    const time = getCurrentTime();
    const match = findDemoAnswer(lecture, content);
    const answer: ChatMessage = match
      ? { id: `answer-${Date.now()}`, role: "assistant", content: match.answer, citationMs: match.citationMs, time }
      : {
          id: `answer-${Date.now()}`,
          role: "assistant",
          content: lecture.isDemoUpload
            ? "纯前端演示不会分析你上传的视频。你可以体验时间跳转，接入真实问答服务后这里会基于转写回答。"
            : "演示问答暂未找到对应内容。可以试试询问 RoPE、正弦位置编码或长度外推。",
          time,
        };
    setMessages((current) => [...current, { id: `question-${Date.now()}`, role: "user", content, time }, answer]);
    setQuestion("");
  };

  return (
    <aside className="chat-panel" aria-label="课程问答">
      <header className="chat-header"><h1>问问这节课</h1><span className="demo-model"><Icon name="sparkles" />演示问答</span></header>
      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && <p className="chat-empty">输入问题体验演示问答。当前不会调用外部模型。</p>}
        {messages.map((message) => (
          <article className={`chat-message chat-message--${message.role}`} key={message.id}>
            <header><strong>{message.role === "user" ? "你" : "演示 AI"}</strong><time>{message.time}</time></header>
            <p>{message.content}</p>
            {message.citationMs !== undefined && (
              <button className="chat-citation" type="button" onClick={() => onSeek(message.citationMs!)}>
                跳到 {formatTimestamp(message.citationMs)}
              </button>
            )}
          </article>
        ))}
      </div>
      <form className="chat-composer" onSubmit={submitQuestion}>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="关于这节课提个问题…" aria-label="课程问题" />
        <button type="submit" aria-label="发送问题"><Icon name="send" /></button>
      </form>
    </aside>
  );
}
