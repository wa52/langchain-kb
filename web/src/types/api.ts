export interface ComponentStatus {
  name: string;
  state: string;
  detail?: string | null;
  duration_ms?: number | null;
  error?: string | null;
}

export interface SystemStatus {
  status: string;
  uptime: number;
  index_version: number;
  vector_count: number;
  entity_count: number;
  bm25_chunks?: number | null;
  components: Record<string, ComponentStatus>;
}

export interface SourceItem {
  source: string;
  chunk_id: string;
  excerpt?: string | null;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  interrupted?: boolean;
  sources?: SourceItem[];
  streaming?: boolean;
  error?: string | null;
}

export type ViewId = "chat" | "knowledge" | "status" | "settings";

export interface SessionSummary {
  id: string;
  title: string;
  created: string;
  turns: number;
  size: number;
}

export interface SessionMessage {
  role: string;
  content: string;
  interrupted?: boolean;
}

export interface SessionDetail {
  id: string;
  messages: SessionMessage[];
}

export interface GraphStats {
  entities: number;
  relations: number;
}

export interface IndexTask {
  task_id: string;
  status: string;
}

export interface TaskStatus {
  task_id: string;
  status: string;
  progress?: string | null;
  result?: { chunks_added?: number } | null;
  error?: string | null;
}

export interface IndexTaskSummary {
  task_id: string;
  status: string;
  progress?: string | null;
  result?: { chunks_added?: number } | null;
  error?: string | null;
}

export interface KnowledgeStats {
  documents: number;
  chunks: number;
  bm25_chunks?: number | null;
  graph: GraphStats;
  index_task?: IndexTaskSummary | null;
}

export interface UploadTasks {
  tasks: IndexTask[];
  saved: string[];
}

export interface DiagnosticsCheck {
  name: string;
  ok: boolean;
  status: string;
  detail: string;
  error?: string | null;
  duration_ms?: number | null;
  fix: string;
  repairable: boolean;
}

export interface DiagnosticsSummary {
  total: number;
  ok: number;
  failed: number;
}

export interface DiagnosticsResult {
  checks: DiagnosticsCheck[];
  summary: DiagnosticsSummary;
}

export interface DiagnosticsTaskStatus {
  task_id: string;
  status: string;
  result?: DiagnosticsResult | null;
  error?: string | null;
}
