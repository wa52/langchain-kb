import { useState } from "react";

import type { SourceItem } from "../../types/api";

const MAX_VISIBLE = 3;

interface SourceChipsProps {
  sources: SourceItem[];
  onOpen: (source: SourceItem) => void;
}

export function SourceChips({ sources, onOpen }: SourceChipsProps) {
  const [expanded, setExpanded] = useState(false);
  const visible = expanded ? sources : sources.slice(0, MAX_VISIBLE);
  const rest = sources.length - MAX_VISIBLE;
  return (
    <div className="source-chips" aria-label="回答来源">
      {visible.map((s) => (
        <button
          key={`${s.source}-${s.chunk_id}`}
          type="button"
          className="chip"
          onClick={() => onOpen(s)}
          title={`查看来源：${s.source}`}
        >
          {s.source}
        </button>
      ))}
      {!expanded && rest > 0 && (
        <button
          type="button"
          className="chip chip-more"
          onClick={() => setExpanded(true)}
          title={`展开全部 ${sources.length} 个来源`}
        >
          +{rest}
        </button>
      )}
      {expanded && sources.length > MAX_VISIBLE && (
        <button
          type="button"
          className="chip chip-more"
          onClick={() => setExpanded(false)}
          title="收起来源"
        >
          收起
        </button>
      )}
    </div>
  );
}
