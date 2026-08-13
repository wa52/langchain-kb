import type { SourceItem } from "../../types/api";

const MAX_VISIBLE = 3;

interface SourceChipsProps {
  sources: SourceItem[];
  onOpen: (source: SourceItem) => void;
}

export function SourceChips({ sources, onOpen }: SourceChipsProps) {
  const visible = sources.slice(0, MAX_VISIBLE);
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
      {rest > 0 && <span className="chip-more">+{rest}</span>}
    </div>
  );
}
