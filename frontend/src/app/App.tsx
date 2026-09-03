import { useEffect, useState } from "react";

import { AppSidebar } from "../components/AppSidebar";
import { ReaderPage } from "../features/reader/ReaderPage";
import { SearchPage } from "../features/search/SearchPage";
import { UploadPage } from "../features/upload/UploadPage";
import { useBackendStatus } from "../hooks/useBackendStatus";
import type { AppView } from "../types/lecture";

const viewFromHash = (): AppView => {
  const view = window.location.hash.slice(1);
  return view === "search" || view === "reader" || view === "upload" ? view : "upload";
};

export default function App() {
  const [currentView, setCurrentView] = useState<AppView>(viewFromHash);
  const backend = useBackendStatus();

  useEffect(() => {
    const syncView = () => setCurrentView(viewFromHash());
    window.addEventListener("hashchange", syncView);
    return () => window.removeEventListener("hashchange", syncView);
  }, []);

  const navigate = (view: AppView) => {
    window.location.hash = view;
  };

  return (
    <div className="application-shell">
      <AppSidebar currentView={currentView} onNavigate={navigate} />
      {currentView === "upload" && <UploadPage backend={backend} />}
      {currentView === "search" && <SearchPage onOpenLecture={() => navigate("reader")} />}
      {currentView === "reader" && <ReaderPage />}
    </div>
  );
}
