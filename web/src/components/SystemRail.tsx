import type { ComponentStatus } from "../types/api";
import { StatusDot } from "./StatusDot";

const RAIL_ORDER = ["embedding", "llm", "vector_store", "bm25", "graph", "agent"];

const RAIL_LABEL: Record<string, string> = {
  embedding: "embedding",
  llm: "llm",
  vector_store: "vector",
  bm25: "bm25",
  graph: "graph",
  agent: "agent",
};

interface SystemRailProps {
  components: Record<string, ComponentStatus>;
  onOpenStatus: () => void;
}

export function SystemRail({ components, onOpenStatus }: SystemRailProps) {
  return (
    <nav
      className="sys-rail"
      aria-label="系统状态链路"
      onClick={onOpenStatus}
      title="查看状态"
    >
      {RAIL_ORDER.map((name) => {
        const state = components[name]?.state ?? "pending";
        return (
          <span key={name} className="rail-item" title={components[name]?.detail ?? name}>
            <StatusDot state={state} />
            <span>{RAIL_LABEL[name] ?? name}</span>
          </span>
        );
      })}
    </nav>
  );
}
