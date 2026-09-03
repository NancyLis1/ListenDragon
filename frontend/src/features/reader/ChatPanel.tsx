import { useState, type FormEvent } from "react";

import { Icon } from "../../components/Icon";
import { initialChat } from "../../data/mockLectures";
import type { ChatMessage } from "../../types/lecture";

function getCurrentTime() {
  return new Intl.DateTimeFormat("zh-CN", { hour: "2-digit", minute: "2-digit", hour12: false }).format(new Date());
}

export function ChatPanel() {
  const [messages, setMessages] = useState<ChatMessage[]>(initialChat);
  const [question, setQuestion] = useState("");

  const submitQuestion = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content) return;
    const time = getCurrentTime();
    setMessages((current) => [...current, { id: `question-${Date.now()}`, role: "user", content, time }, { id: `answer-${Date.now()}`, role: "assistant", content: "我会结合当前视频的转写、幻灯片和时间戳来回答这个问题。后端问答服务接入后，这里将返回带可追溯引用的完整答案。", time }]);
    setQuestion("");
  };

  return (
    <aside className="chat-panel" aria-label="课程问答">
      <header className="chat-header"><h1>问问这节课</h1><button type="button"><Icon name="sparkles" />GPT-4o⌄</button></header>
      <div className="chat-messages">
        {messages.map((message) => (
          <article className={`chat-message chat-message--${message.role}`} key={message.id}>
            <header><strong>{message.role === "user" ? "你" : "AI"}</strong><time>{message.time}</time></header>
            <p>{message.content}</p>
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
