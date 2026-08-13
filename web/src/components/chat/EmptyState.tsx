interface EmptyStateProps {
  knowledgeEmpty: boolean;
  onAddMaterials: () => void;
}

export function EmptyState({ knowledgeEmpty, onAddMaterials }: EmptyStateProps) {
  if (knowledgeEmpty) {
    return (
      <div className="empty-state">
        <h2>知识库还没有资料</h2>
        <p>
          添加文档后，Agent 会基于你的资料回答问题、引用来源并关联图谱。
        </p>
        <button type="button" className="primary" onClick={onAddMaterials}>
          添加资料
        </button>
        <p className="hint">也可以先直接聊天，但回答不会包含本地知识库引用。</p>
      </div>
    );
  }
  return (
    <div className="empty-state">
      <h2>开始对话</h2>
      <p>输入问题，Agent 会基于知识库内容回答，并标注来源。</p>
    </div>
  );
}
