import { useState, type FormEvent } from "react";

import { Icon } from "../../components/Icon";
import { initialChat } from "../../data/mockLectures";
import { askQuestion, createConversation } from "../../lib/api";
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
  const [messages, setMessages] = useState<ChatMessage[]>(lecture.isRemote ? [] : initialChat);
  const [question, setQuestion] = useState("");
  const [conversationId, setConversationId] = useState<string>();
  const [isSending, setIsSending] = useState(false);
  const [error, setError] = useState("");

  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content) return;
    const time = getCurrentTime();
    setMessages((current) => [...current, { id: `question-${Date.now()}`, role: "user", content, time }]);
    setQuestion("");
    setError("");
    if (!lecture.isRemote) {
      const match = findDemoAnswer(lecture, content);
      const answer: ChatMessage = match
        ? { id: `answer-${Date.now()}`, role: "assistant", content: match.answer, citationMs: match.citationMs, time }
        : { id: `answer-${Date.now()}`, role: "assistant", content: "体验问答暂未找到对应内容。可以试试询问 RoPE、正弦位置编码或长度外推。", time };
      setMessages((current) => [...current, answer]);
      return;
    }
    setIsSending(true);
    try {
      const activeConversation = conversationId || await createConversation(lecture.id);
      if (!conversationId) setConversationId(activeConversation);
      const result = await askQuestion(activeConversation, content);
      setMessages((current) => [...current, {
        id: result.message_id,
        role: "assistant",
        content: result.answer,
        time: getCurrentTime(),
        citations: result.evidence.map((item) => ({
          chunkId: item.chunk_id,
          startMs: item.start_ms,
          endMs: item.end_ms,
          text: item.text,
        })),
      }]);
    } catch (requestError) {
      setError(requestError instanceof Error ? requestError.message : "问答请求失败。");
    } finally {
      setIsSending(false);
    }
  };

  return (
    <aside className="chat-panel" aria-label="课程问答">
      <header className="chat-header"><h1>问问这节课</h1><span className="demo-model"><Icon name="sparkles" />{lecture.isRemote ? "有据问答" : "体验问答"}</span></header>
      <div className="chat-messages" aria-live="polite">
        {messages.length === 0 && <p className="chat-empty">{lecture.isRemote ? "问题将基于视频转写回答，并附带可跳转证据。" : "输入问题体验样例问答。"}</p>}
        {messages.map((message) => (
          <article className={`chat-message chat-message--${message.role}`} key={message.id}>
            <header><strong>{message.role === "user" ? "你" : lecture.isRemote ? "ListenDragon" : "体验 AI"}</strong><time>{message.time}</time></header>
            <p>{message.content}</p>
            {message.citationMs !== undefined && (
              <button className="chat-citation" type="button" onClick={() => onSeek(message.citationMs!)}>
                跳到 {formatTimestamp(message.citationMs)}
              </button>
            )}
            {message.citations?.map((citation) => (
              <button className="chat-citation" type="button" key={citation.chunkId} onClick={() => onSeek(citation.startMs)} title={citation.text}>
                跳到 {formatTimestamp(citation.startMs)}
              </button>
            ))}
          </article>
        ))}
      </div>
      {isSending && <p className="chat-empty">正在检索并核验答案…</p>}
      {error && <p className="chat-empty reader-error" role="alert">{error}</p>}
      <form className="chat-composer" onSubmit={(event) => void submitQuestion(event)}>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="关于这节课提个问题…" aria-label="课程问题" disabled={isSending} />
        <button type="submit" aria-label="发送问题" disabled={isSending}><Icon name="send" /></button>
      </form>
    </aside>
  );
}
