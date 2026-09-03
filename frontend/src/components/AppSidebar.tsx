import { Icon, type IconName } from "./Icon";
import type { AppView } from "../types/lecture";

interface AppSidebarProps {
  currentView: AppView;
  onNavigate: (view: AppView) => void;
}

const navigation: Array<{ view: AppView; label: string; icon: IconName }> = [
  { view: "upload", label: "上传视频", icon: "upload" },
  { view: "search", label: "检索内容", icon: "search" },
  { view: "reader", label: "课程阅读", icon: "file" },
];

export function AppSidebar({ currentView, onNavigate }: AppSidebarProps) {
  return (
    <aside className={`app-sidebar app-sidebar--${currentView}`}>
      <button className="brand-mark" type="button" onClick={() => onNavigate("upload")} aria-label="返回 ListenDragon 首页">LD</button>
      <nav className="primary-nav" aria-label="主导航">
        {navigation.map((item) => (
          <button
            className={`nav-item ${currentView === item.view ? "is-active" : ""}`}
            type="button"
            key={item.view}
            onClick={() => onNavigate(item.view)}
          >
            <Icon name={item.icon} />
            <span>{item.label}</span>
          </button>
        ))}
      </nav>
      <div className="sidebar-footer">
        <button className="nav-item" type="button" aria-label="设置"><Icon name="settings" /><span>设置</span></button>
        <div className="avatar" aria-label="当前用户">S</div>
      </div>
    </aside>
  );
}
