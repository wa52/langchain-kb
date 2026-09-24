import { useEffect, useRef, useState } from "react";

import { setAuthRequiredHandler } from "./api/client";
import { DeveloperPane } from "./components/DeveloperPane";
import { SystemRail } from "./components/SystemRail";
import { TokenDialog } from "./components/TokenDialog";
import { useDeveloperMode } from "./hooks/useDeveloperMode";
import { useSystemStatus } from "./hooks/useSystemStatus";
import { ChatPage } from "./pages/ChatPage";
import { CapabilitiesPage } from "./pages/CapabilitiesPage";
import { EvaluationPage } from "./pages/EvaluationPage";
import { KnowledgePage } from "./pages/KnowledgePage";
import { RetrievalPage } from "./pages/RetrievalPage";
import { SettingsPage } from "./pages/SettingsPage";
import { StatusPage } from "./pages/StatusPage";
import { TraceViewerPage } from "./pages/TraceViewerPage";
import type { SystemStatus, ViewId } from "./types/api";

const NAV_ITEMS: Array<{ id: ViewId; label: string }> = [
  { id: "chat", label: "Chat" },
  { id: "knowledge", label: "知识库" },
  { id: "retrieval", label: "检索调试" },
  { id: "evaluation", label: "评测" },
  { id: "capabilities", label: "能力" },
  { id: "traces", label: "Trace" },
  { id: "status", label: "状态" },
  { id: "settings", label: "设置" },
];

interface PageProps {
  status: SystemStatus | null;
  onNavigate?: (view: ViewId) => void;
}

export default function App() {
  const [view, setView] = useState<ViewId>("chat");
  const [tokenDialogOpen, setTokenDialogOpen] = useState(false);
  const [devMode, toggleDevMode] = useDeveloperMode();
  const authDismissedRef = useRef(false);
  const { status } = useSystemStatus();

  useEffect(() => {
    setAuthRequiredHandler(() => {
      if (!authDismissedRef.current) setTokenDialogOpen(true);
    });
    return () => setAuthRequiredHandler(null);
  }, []);

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
        <button
          type="button"
          className={devMode ? "dev-toggle active" : "dev-toggle"}
          aria-pressed={devMode}
          onClick={toggleDevMode}
          title="开发者模式"
        >
          开发者
        </button>
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
          ) : view === "retrieval" ? (
            <RetrievalPage />
          ) : view === "evaluation" ? (
            <EvaluationPage />
          ) : view === "capabilities" ? (
            <CapabilitiesPage onOpenSettings={() => navigate("settings")} />
          ) : view === "traces" ? (
            <TraceViewerPage />
          ) : view === "status" ? (
            <StatusPage {...pageProps} />
          ) : (
            <SettingsPage
              onOpenTokenDialog={() => {
                authDismissedRef.current = false;
                setTokenDialogOpen(true);
              }}
            />
          )}
        </main>
        {devMode ? <DeveloperPane /> : null}
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

      {tokenDialogOpen ? (
        <TokenDialog
          onClose={() => {
            authDismissedRef.current = true;
            setTokenDialogOpen(false);
          }}
        />
      ) : null}
    </div>
  );
}
