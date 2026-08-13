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
