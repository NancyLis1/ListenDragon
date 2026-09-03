import { useState } from "react";

import { Icon } from "../../components/Icon";
import { transcript } from "../../data/mockLectures";

export function Transcript() {
  const [activeTime, setActiveTime] = useState("12:47");
  const [noteOpen, setNoteOpen] = useState(false);

  return (
    <section className="transcript-panel" aria-label="课程转写">
      {transcript.slice(0, 4).map((item) => (
        <button className={`transcript-line ${activeTime === item.time ? "is-active" : ""}`} type="button" key={item.time} onClick={() => setActiveTime(item.time)}>
          <time>{item.time}</time><span>{item.content}</span>
        </button>
      ))}
      <div className="inline-note">
        <div><strong>我的笔记</strong><button type="button" onClick={() => setNoteOpen((open) => !open)} aria-label="编辑笔记"><Icon name="note" /></button></div>
        {noteOpen ? <textarea defaultValue="重要：假设必须是可证伪的。" aria-label="课程笔记" autoFocus /> : <p>重要：假设必须是可证伪的。</p>}
      </div>
      {transcript.slice(4).map((item) => (
        <button className={`transcript-line ${activeTime === item.time ? "is-active" : ""}`} type="button" key={item.time} onClick={() => setActiveTime(item.time)}>
          <time>{item.time}</time><span>{item.content}</span>
        </button>
      ))}
    </section>
  );
}
