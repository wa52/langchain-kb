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
  hit_chain?: string[];
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

export interface TrackedFile {
  source_type: string;
  file_key: string;
  hash: string;
}

export interface TrackedFilesResponse {
  files: TrackedFile[];
  total: number;
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

export interface AppSettings {
  knowledge_home: string;
  data_dir: string;
  external_dir: string;
  chroma_persist_dir: string;
  chroma_ok: boolean;
  graph_persist_dir: string;
  embedding_model: string;
  embedding_device: string;
  llm_model: string;
  llm_api_base: string;
  llm_api_configured: boolean;
  rerank_llm: string;
  local_llm_base: string;
  local_llm_model: string;
  hf_endpoint: string;
  hf_offline: boolean;
  graph_enabled: boolean;
  graph_llm_extraction: boolean;
  hybrid_search: boolean;
  grading: boolean;
  rewrite: boolean;
  context_compression: boolean;
  chunk_size: number;
  chunk_overlap: number;
  top_k: number;
  max_context_tokens: number;
  mcp_config_path: string;
  mcp_enabled: boolean;
  lan_protection: boolean;
}
