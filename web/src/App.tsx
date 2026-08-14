import { useState } from "react";

import { SystemRail } from "./components/SystemRail";
import { useSystemStatus } from "./hooks/useSystemStatus";
import { ChatPage } from "./pages/ChatPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatusPage } from "./pages/StatusPage";
import type { SystemStatus, ViewId } from "./types/api";

const NAV_ITEMS: Array<{ id: ViewId; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "knowledge", label: "知识库" },
  { id: "status", label: "状态" },
  { id: "settings", label: "设置" },
];

interface PageProps {
  status: SystemStatus | null;
  onNavigate?: (view: ViewId) => void;
}

export default function App() {
  const [view, setView] = useState<ViewId>("chat");
  const { status } = useSystemStatus();

  function navigate(v: ViewId): void {
    setView(v);
  }

  const pageProps: PageProps = { status, onNavigate: navigate };

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">Knowledge Agent</div>
        <SystemRail
          components={status?.components ?? {}}
          onOpenStatus={() => navigate("status")}
        />
      </header>

      <div className="app-body">
        <nav className="side-nav" aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
              onClick={() => navigate(item.id)}
            >
              {item.label}
            </button>
          ))}
        </nav>
        <main className="workspace">
          {view === "chat" ? (
            <ChatPage {...pageProps} onNavigate={(v) => navigate(v)} />
          ) : view === "knowledge" ? (
            <KnowledgePage />
          ) : view === "status" ? (
            <StatusPage {...pageProps} />
          ) : (
            <SettingsPage {...pageProps} />
          )}
        </main>
      </div>

      <nav className="mobile-tabs" aria-label="主导航">
        {NAV_ITEMS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={view === item.id ? "active" : ""}
            aria-current={view === item.id ? "page" : undefined}
            onClick={() => navigate(item.id)}
          >
            {item.label}
          </button>
        ))}
      </nav>
    </div>
  );
}
