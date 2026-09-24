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

export interface TraceEvent {
  type: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface AgentTrace {
  run_id: string;
  query: string;
  selected_tools: string[];
  llm_calls?: Array<Record<string, unknown>>;
  tool_calls?: Array<Record<string, unknown>>;
  events: TraceEvent[];
}

export interface FastRagTrace {
  route: "fast_rag" | "direct";
  total_ms: number;
  stages: Record<string, number>;
  llm_calls: number;
  raw_docs_count: number;
  selected_docs_count: number;
  context_tokens: number;
  relevant: boolean;
  routing?: {
    route: string;
    confidence: number;
    reasons: string[];
    signals: Record<string, number | boolean>;
  };
}

export type ViewId = "chat" | "knowledge" | "retrieval" | "evaluation" | "capabilities" | "traces" | "status" | "settings";

export interface CapabilityTool {
  name: string;
  description: string;
  source: "local" | "mcp" | "plugin";
  server_id: string | null;
  tags: string[];
  risk_level: string;
  read_only: boolean;
  retryable: boolean;
  enabled: boolean;
}

export interface CapabilityMcpServer {
  name: string;
  type: string;
  enabled: boolean;
  status: "ready" | "discovering" | "degraded" | "not_started" | "disabled";
}

export interface CapabilityCatalog {
  tools: CapabilityTool[];
  mcp_servers: CapabilityMcpServer[];
  summary: { tools: number; mcp_servers: number; ready: number; degraded: number };
}

export interface RetrievalDebugResult {
  source: string;
  chunk_id: string;
  content: string;
  dense_score: number;
  bm25_score: number;
  fusion_score: number;
  dense_rank: number | null;
  bm25_rank: number | null;
  rank: number;
}

export interface RetrievalDebugResponse {
  query: string;
  results: RetrievalDebugResult[];
  elapsed_ms: number;
}

export interface RetrievalEvaluationCaseResult {
  case_id: string;
  relevant_ids: string[];
  retrieved_relevant_ids: string[];
  first_relevant_rank: number | null;
  hits_at_k: Record<string, number>;
  reciprocal_rank: number;
  elapsed_ms: number;
}

export interface RetrievalEvaluationMetrics {
  total: number;
  recall_at_k: Record<string, number>;
  mrr: number;
  latency_ms: { p50: number; p95: number };
  cases: RetrievalEvaluationCaseResult[];
}

export interface RetrievalEvaluationReport {
  report_version: number;
  evaluated_at: string;
  environment: string;
  dataset_version: number;
  dataset_sha256: string;
  retrieval_profile: string;
  embedding_model: string;
  chunking: { size: number; overlap: number };
  corpus: Array<{ source: string; sha256: string }>;
  metrics: RetrievalEvaluationMetrics;
}

export interface RetrievalEvaluationLatestResponse {
  status: "empty" | "completed";
  report: RetrievalEvaluationReport | null;
  message: string | null;
}

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

export interface McpServerSummary {
  name: string;
  type: string;
  enabled: boolean;
  target: string;
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
  llm_provider: string;
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
  jev_api_configured: boolean;
  mcp_servers: McpServerSummary[];
  mcp_http_available: boolean;
  mcp_http_error: string | null;
  lan_protection: boolean;
}
