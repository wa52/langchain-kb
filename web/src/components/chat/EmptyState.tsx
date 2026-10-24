interface EmptyStateProps {
  knowledgeEmpty: boolean;
  connection: "loading" | "unavailable" | "ready";
  onAddMaterials: () => void;
}

export function EmptyState({ knowledgeEmpty, connection, onAddMaterials }: EmptyStateProps) {
  if (connection !== "ready") {
    const unavailable = connection === "unavailable";
    return (
      <div className={`empty-state ${unavailable ? "is-unavailable" : "is-loading"}`} role="status">
        <span className="empty-symbol" aria-hidden="true">
          <svg viewBox="0 0 32 32" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M7 11.5a11 11 0 0 1 18 0M11 16a5.5 5.5 0 0 1 10 0" />
            {unavailable ? <path d="M6 26 26 6" /> : <circle cx="16" cy="23" r="1" fill="currentColor" stroke="none" />}
          </svg>
        </span>
        <span className="empty-kicker">{unavailable ? "连接状态 / 未连接" : "连接状态 / 检查中"}</span>
        <h2>{unavailable ? "知识库服务尚未连接" : "正在连接知识库"}</h2>
        <p>{unavailable
          ? "请检查服务是否已启动及网络连接。连接恢复后，资料和可用能力会自动显示。"
          : "正在读取资料与可用能力，请稍候。"}</p>
      </div>
    );
  }

  if (knowledgeEmpty) {
    return (
      <div className="empty-state">
        <img className="empty-mark" src="/assets/knowledge-agent.svg" alt="" aria-hidden="true" />
        <h2>知识库还没有资料</h2>
        <p>
          添加文档后，Agent 会基于你的资料回答问题、引用来源并关联图谱。
        </p>
        <button type="button" className="primary ui-hint" data-hint="打开知识库，添加需要检索的资料" onClick={onAddMaterials}>
          <span aria-hidden="true">＋</span> 添加资料
        </button>
        <p className="hint">也可以先直接聊天，但回答不会包含知识库引用。</p>
      </div>
    );
  }
  return (
    <div className="empty-state">
      <img className="empty-mark" src="/assets/knowledge-agent.svg" alt="" aria-hidden="true" />
      <span className="empty-kicker">知识已就绪</span>
      <h2>从一个问题开始</h2>
      <p>询问知识库中的技术资料、验证一个想法，或让 Agent 调用可用工具。回答会尽可能标注证据来源。</p>
      <div className="empty-capabilities" aria-label="支持的任务"><span>知识检索</span><span>来源追溯</span><span>工具协作</span></div>
    </div>
  );
}
