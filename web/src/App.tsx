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

const NAV_ITEMS: Array<{ id: ViewId; label: string; hint: string }> = [
  { id: "chat", label: "对话", hint: "打开知识问答与 Agent 对话" },
  { id: "knowledge", label: "知识库", hint: "管理资料与索引" },
  { id: "retrieval", label: "检索调试", hint: "测试检索结果与评分" },
  { id: "evaluation", label: "评测", hint: "查看质量评测结果" },
  { id: "capabilities", label: "能力", hint: "查看工具与 MCP 能力" },
  { id: "traces", label: "执行追踪", hint: "查看 Agent 执行链路" },
  { id: "status", label: "状态", hint: "查看服务运行状态" },
  { id: "settings", label: "设置", hint: "配置服务与模型" },
];

function NavIcon({ id }: { id: ViewId }) {
  const paths: Record<ViewId, React.ReactNode> = {
    chat: <><path d="M4 5h16v11H9l-5 4V5Z"/><path d="M8 9h8M8 12h5"/></>,
    knowledge: <><path d="M4 5.5C7 4 9.5 4 12 6v14c-2.5-2-5-2-8-.5v-14ZM20 5.5c-3-1.5-5.5-1.5-8 .5v14c2.5-2 5-2 8-.5v-14Z"/></>,
    retrieval: <><circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5M8 10.5h5"/></>,
    evaluation: <><path d="M4 19h16M7 16V9m5 7V5m5 11v-5"/></>,
    capabilities: <><path d="M9 3h6l1 3 3 1 2 3-2 3 1 3-3 2-3-1-2 3-3-2-3 1-2-3 1-3-2-3 2-3 3-1 1-3Z"/><circle cx="12" cy="11.5" r="2.5"/></>,
    traces: <><circle cx="5" cy="5" r="2"/><circle cx="19" cy="12" r="2"/><circle cx="5" cy="19" r="2"/><path d="M7 5h5v7h5M7 19h5v-7"/></>,
    status: <><path d="M3 12h4l2.5-6 4 12 2.5-6h5"/></>,
    settings: <><circle cx="12" cy="12" r="3"/><path d="M12 2v3m0 14v3M2 12h3m14 0h3M4.9 4.9 7 7m10 10 2.1 2.1M19.1 4.9 17 7M7 17l-2.1 2.1"/></>,
  };
  return <svg className="nav-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[id]}</svg>;
}

interface PageProps {
  status: SystemStatus | null;
  onNavigate?: (view: ViewId) => void;
}

export default function App() {
  const [view, setView] = useState<ViewId>("chat");
  const [mobileNavOpen, setMobileNavOpen] = useState(false);
  const [tokenDialogOpen, setTokenDialogOpen] = useState(false);
  const [devMode, toggleDevMode] = useDeveloperMode();
  const authDismissedRef = useRef(false);
  const { status, error: statusError } = useSystemStatus();

  useEffect(() => {
    setAuthRequiredHandler(() => {
      if (!authDismissedRef.current) setTokenDialogOpen(true);
    });
    return () => setAuthRequiredHandler(null);
  }, []);

  function navigate(v: ViewId): void {
    setView(v);
    setMobileNavOpen(false);
  }

  const pageProps: PageProps = { status, onNavigate: navigate };

  return (
    <div className="app">
      <header className="app-header">
        <button type="button" className="mobile-nav-toggle ui-hint" data-hint="展开或收起主导航" aria-label="主导航" aria-expanded={mobileNavOpen} aria-controls="primary-nav" onClick={() => setMobileNavOpen((open) => !open)}>
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16"/></svg>
        </button>
        <div className="brand"><img className="brand-mark" src="/assets/knowledge-agent.svg" alt="" aria-hidden="true" /><span>Knowledge Agent</span></div>
        <SystemRail
          components={status?.components ?? {}}
        />
        <button
          type="button"
          className={devMode ? "dev-toggle active" : "dev-toggle"}
          aria-pressed={devMode}
          onClick={toggleDevMode}
          title="开发者模式"
          data-hint="显示或隐藏开发者调试面板"
        >
          <span aria-hidden="true">⌁</span> 开发者
        </button>
      </header>

      <div className="app-body">
        {mobileNavOpen ? <button type="button" className="mobile-nav-backdrop" aria-label="关闭主导航" onClick={() => setMobileNavOpen(false)} /> : null}
        <nav id="primary-nav" className={mobileNavOpen ? "side-nav mobile-open" : "side-nav"} aria-label="主导航">
          {NAV_ITEMS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={view === item.id ? "active" : ""}
              aria-current={view === item.id ? "page" : undefined}
              data-hint={item.hint}
              onClick={() => navigate(item.id)}
            >
              <NavIcon id={item.id} /><span>{item.label}</span>
            </button>
          ))}
        </nav>
        <main className="workspace">
          {view === "chat" ? (
            <ChatPage {...pageProps} statusError={statusError} onNavigate={(v) => navigate(v)} />
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
