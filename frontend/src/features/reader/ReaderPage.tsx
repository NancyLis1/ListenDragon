import { ChatPanel } from "./ChatPanel";
import { LectureVideo } from "./LectureVideo";
import { Transcript } from "./Transcript";

export function ReaderPage() {
  return (
    <main className="reader-page page-content">
      <section className="reader-main"><LectureVideo /><Transcript /></section>
      <ChatPanel />
    </main>
  );
}
