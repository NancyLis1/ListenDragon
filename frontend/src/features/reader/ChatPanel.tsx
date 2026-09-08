import { useEffect, useRef, useState, type FormEvent } from "react";

import { Icon } from "../../components/Icon";
import { initialChat } from "../../data/mockLectures";
import { ApiError, askQuestion, createConversation, getConversation } from "../../lib/api";
import { readSaved, saveLocal } from "../../lib/persistence";
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
  const storageKey = `conversation:${lecture.id}`;
  const [isRestoring, setIsRestoring] = useState(Boolean(lecture.isRemote && readSaved(storageKey)));
  const [restoreFailed, setRestoreFailed] = useState(false);
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    const controller = new AbortController();
    const saved = lecture.isRemote ? readSaved(storageKey) : undefined;
    if (saved) {
      setIsRestoring(true);
      void getConversation(saved, controller.signal).then((result) => {
        if (controller.signal.aborted) return;
        if (result.video_id !== lecture.id) throw new Error("保存的会话与当前视频不匹配，请新建会话。");
        setConversationId(result.conversation_id);
        setMessages(result.messages.map((message) => ({
          id: message.message_id, role: message.role, content: message.content,
          time: new Date(message.created_at).toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" }),
          citations: message.evidence.map((item) => ({ chunkId: item.chunk_id, startMs: item.start_ms, endMs: item.end_ms, text: item.text })),
        })));
      }).catch((requestError) => {
        if (controller.signal.aborted) return;
        if (requestError instanceof ApiError && requestError.status === 404) saveLocal(storageKey, "");
        else {
          setRestoreFailed(true);
          setError("会话恢复失败，请刷新重试或新建会话。");
        }
      }).finally(() => { if (!controller.signal.aborted) setIsRestoring(false); });
    }
    return () => { mounted.current = false; controller.abort(); };
  }, [lecture.id, lecture.isRemote, storageKey]);

  const newConversation = async () => {
    if (isSending || isRestoring) return;
    setIsSending(true);
    setError("");
    try {
      const id = await createConversation(lecture.id);
      saveLocal(storageKey, id);
      if (!mounted.current) return;
      setConversationId(id);
      setRestoreFailed(false);
      setMessages([]);
      setQuestion("");
    } catch (requestError) {
      if (mounted.current) setError(requestError instanceof Error ? requestError.message : "新建会话失败。");
    } finally { if (mounted.current) setIsSending(false); }
  };

  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const content = question.trim();
    if (!content || isSending || isRestoring || restoreFailed) return;
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
      saveLocal(storageKey, activeConversation);
      if (!mounted.current) return;
      if (!conversationId) setConversationId(activeConversation);
      const result = await askQuestion(activeConversation, content);
      if (!mounted.current) return;
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
      if (mounted.current) setError(requestError instanceof Error ? requestError.message : "问答请求失败。");
    } finally {
      if (mounted.current) setIsSending(false);
    }
  };

  return (
    <aside className="chat-panel" aria-label="课程问答">
      <header className="chat-header"><h1>问问这节课</h1><span className="demo-model"><Icon name="sparkles" />{lecture.isRemote ? "有据问答" : "体验问答"}</span></header>
      {lecture.isRemote && <button type="button" className="outline-button" onClick={() => void newConversation()} disabled={isSending || isRestoring}>新建会话</button>}
      {isRestoring && <p className="chat-empty">正在恢复会话…</p>}
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
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder="关于这节课提个问题…" aria-label="课程问题" maxLength={1000} disabled={isSending || isRestoring || restoreFailed} />
        <button type="submit" aria-label="发送问题" disabled={isSending || isRestoring || restoreFailed}><Icon name="send" /></button>
      </form>
    </aside>
  );
}
