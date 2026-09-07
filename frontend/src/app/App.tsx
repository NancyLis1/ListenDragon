import { useEffect, useRef, useState } from "react";

import { AppSidebar } from "../components/AppSidebar";
import { lectures } from "../data/mockLectures";
import { ReaderPage } from "../features/reader/ReaderPage";
import { SearchPage } from "../features/search/SearchPage";
import { UploadPage } from "../features/upload/UploadPage";
import type { AppView, LectureDetail } from "../types/lecture";

const viewFromHash = (): AppView => {
  const view = window.location.hash.slice(1);
  return view === "search" || view === "reader" || view === "upload" ? view : "upload";
};

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>(viewFromHash);
  const [courseLibrary, setCourseLibrary] = useState(lectures);
  const [activeLectureId, setActiveLectureId] = useState(lectures[0].id);
  const [readerStartMs, setReaderStartMs] = useState(lectures[0].timestampMs);
  const sessionVideoUrls = useRef<string[]>([]);
  const activeLecture = courseLibrary.find((lecture) => lecture.id === activeLectureId) ?? courseLibrary[0];

  useEffect(() => {
    const syncView = () => setCurrentView(viewFromHash());
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  useEffect(() => () => {
    sessionVideoUrls.current.forEach((url) => URL.revokeObjectURL(url));
  }, []);

  const navigate = (view: AppView) => {
    window.location.hash = view;
  };

  const openLecture = (lectureId: string, timeMs: number) => {
    setActiveLectureId(lectureId);
    setReaderStartMs(timeMs);
    navigate("reader");
  };

  const addUploadedLecture = (lecture: LectureDetail) => {
    if (lecture.videoUrl) sessionVideoUrls.current.push(lecture.videoUrl);
    setCourseLibrary((current) => [lecture, ...current]);
    openLecture(lecture.id, 0);
  };

  return (
    <div className="application-shell">
      <AppSidebar currentView={currentView} onNavigate={navigate} />
      {currentView === "upload" && <UploadPage onComplete={addUploadedLecture} />}
      {currentView === "search" && <SearchPage lectures={courseLibrary} onOpenLecture={openLecture} />}
      {currentView === "reader" && <ReaderPage lecture={activeLecture} initialTimeMs={readerStartMs} />}
    </div>
  );
}
