interface EmptyStateProps {
  knowledgeEmpty: boolean;
  onAddMaterials: () => void;
}

export function EmptyState({ knowledgeEmpty, onAddMaterials }: EmptyStateProps) {
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
        <p className="hint">也可以先直接聊天，但回答不会包含本地知识库引用。</p>
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
