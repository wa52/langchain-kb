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
}

export function SystemRail({ components }: SystemRailProps) {
  return (
    <div
      className="sys-rail"
      aria-label="系统组件状态"
    >
      {RAIL_ORDER.map((name) => {
        const state = components[name]?.state ?? "pending";
        return (
          <span key={name} className="rail-item" aria-label={`${RAIL_LABEL[name] ?? name}：${state}`} title={components[name]?.detail ?? name}>
            <StatusDot state={state} />
            <span>{RAIL_LABEL[name] ?? name}</span>
          </span>
        );
      })}
    </div>
  );
}
