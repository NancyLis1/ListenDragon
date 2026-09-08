import { useEffect, useRef, useState } from "react";

import { AppSidebar } from "../components/AppSidebar";
import { lectures } from "../data/mockLectures";
import { ReaderPage } from "../features/reader/ReaderPage";
import { SearchPage } from "../features/search/SearchPage";
import { UploadPage } from "../features/upload/UploadPage";
import { formatTimestamp } from "../features/reader/LectureVideo";
import { checkBackend, listVideos, videoContentUrl, type ApiVideo, type BackendStatus } from "../lib/api";
import type { AppView, LectureDetail } from "../types/lecture";
import { readSaved, saveLocal } from "../lib/persistence";

const viewFromHash = (): AppView => {
  const view = window.location.hash.slice(1);
  return view === "search" || view === "reader" || view === "upload" ? view : "upload";
};

export function videoToLecture(video: ApiVideo): LectureDetail {
  const durationMs = video.duration_ms ?? 1000;
  const title = video.original_name.replace(/\.[^.]+$/, "") || video.original_name;
  return {
    id: video.video_id,
    title,
    source: "ListenDragon · 已上传课程",
    year: new Date(video.created_at).getFullYear().toString(),
    duration: video.duration_ms ? formatTimestamp(durationMs) : "处理中",
    durationMs,
    timeRange: "等待检索",
    timestamp: "0:00",
    timestampMs: 0,
    preview: "视频已完成转写和索引，可查看转写、生成摘要或进行问答。",
    visual: "science",
    videoUrl: videoContentUrl(video.video_id),
    transcript: [],
    summary: { overview: "摘要将在首次打开摘要页时生成。", keyPoints: [], chapters: [] },
    qaRules: [],
    isRemote: true,
  };
}

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>(viewFromHash);
  const [courseLibrary, setCourseLibrary] = useState(lectures);
  const [activeLectureId, setActiveLectureId] = useState(() => readSaved("active-video") || lectures[0].id);
  const [readerStartMs, setReaderStartMs] = useState(0);
  const [backendStatus, setBackendStatus] = useState<BackendStatus>("checking");
  const [libraryLoading, setLibraryLoading] = useState(true);
  const loadToken = useRef(0);
  const activeLecture = courseLibrary.find((lecture) => lecture.id === activeLectureId) ?? courseLibrary[0];

  useEffect(() => {
    const syncView = () => setCurrentView(viewFromHash());
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  const refreshLibrary = async () => {
    const token = ++loadToken.current;
    const status = await checkBackend();
    if (token !== loadToken.current) return;
    setBackendStatus(status);
    if (status === "offline") {
      setCourseLibrary(lectures);
      setLibraryLoading(false);
      return;
    }
    try {
      const videos = await listVideos();
      if (token !== loadToken.current) return;
      const ready = videos.filter((video) => video.state === "READY").map(videoToLecture);
      setCourseLibrary(ready.length ? ready : lectures);
    } catch {
      if (token !== loadToken.current) return;
      setBackendStatus("offline");
      setCourseLibrary(lectures);
    } finally {
      if (token === loadToken.current) setLibraryLoading(false);
    }
  };

  useEffect(() => {
    void refreshLibrary();
    return () => { loadToken.current += 1; };
  }, []);

  const navigate = (view: AppView) => {
    window.location.hash = view;
  };

  const openLecture = (lectureId: string, timeMs: number) => {
    saveLocal("active-video", lectureId);
    setActiveLectureId(lectureId);
    setReaderStartMs(timeMs);
    navigate("reader");
  };

  const addUploadedLecture = (video: ApiVideo) => {
    const lecture = videoToLecture(video);
    setCourseLibrary((current) => [
      lecture,
      ...current.filter((item) => item.isRemote && item.id !== lecture.id),
    ]);
    openLecture(lecture.id, 0);
  };

  return (
    <div className="application-shell">
      <AppSidebar currentView={currentView} onNavigate={navigate} />
      {currentView === "upload" && <UploadPage backendStatus={backendStatus} onComplete={addUploadedLecture} />}
      {currentView === "search" && (libraryLoading ? <main>正在恢复课程…</main> : <SearchPage lectures={courseLibrary} onOpenLecture={openLecture} />)}
      {currentView === "reader" && (libraryLoading ? <main>正在恢复课程…</main> : <ReaderPage key={activeLecture.id} lecture={activeLecture} initialTimeMs={readerStartMs} />)}
    </div>
  );
}
