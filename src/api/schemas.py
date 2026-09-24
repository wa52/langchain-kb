from pydantic import BaseModel, Field, model_validator


class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    uptime: float
    index_version: int
    vector_count: int
    entity_count: int


class ComponentStatus(BaseModel):
    name: str
    state: str
    detail: str | None = None
    duration_ms: float | None = None
    error: str | None = None


class SystemStatusResponse(BaseModel):
    status: str
    uptime: float
    index_version: int
    vector_count: int
    entity_count: int
    bm25_chunks: int | None = None
    components: dict[str, ComponentStatus]


class SearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, examples=["什么是知识库？"])
    top_k: int = Field(default=5, ge=1, le=50)


class SearchResultItem(BaseModel):
    source: str
    chunk_id: str
    score: float
    content: str


class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    elapsed_ms: float


class RetrievalDebugResultItem(BaseModel):
    source: str
    chunk_id: str
    content: str
    dense_score: float
    bm25_score: float
    fusion_score: float
    dense_rank: int | None = None
    bm25_rank: int | None = None
    rank: int


class RetrievalDebugResponse(BaseModel):
    query: str
    results: list[RetrievalDebugResultItem]
    elapsed_ms: float


class RetrievalEvaluationCaseResultResponse(BaseModel):
    case_id: str
    relevant_ids: list[str]
    retrieved_relevant_ids: list[str]
    first_relevant_rank: int | None
    hits_at_k: dict[str, int]
    reciprocal_rank: float
    elapsed_ms: float


class RetrievalEvaluationMetricsResponse(BaseModel):
    total: int
    recall_at_k: dict[str, float]
    mrr: float
    latency_ms: dict[str, float]
    cases: list[RetrievalEvaluationCaseResultResponse]


class RetrievalEvaluationCorpusFileResponse(BaseModel):
    source: str
    sha256: str


class RetrievalEvaluationReportResponse(BaseModel):
    report_version: int
    evaluated_at: str
    environment: str
    dataset_version: int
    dataset_sha256: str
    retrieval_profile: str
    embedding_model: str
    chunking: dict[str, int]
    corpus: list[RetrievalEvaluationCorpusFileResponse]
    metrics: RetrievalEvaluationMetricsResponse


class RetrievalEvaluationLatestResponse(BaseModel):
    status: str
    report: RetrievalEvaluationReportResponse | None = None
    message: str | None = None


class CapabilityToolResponse(BaseModel):
    name: str
    description: str = ""
    source: str
    server_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    risk_level: str
    read_only: bool
    retryable: bool
    enabled: bool


class CapabilityMcpServerResponse(BaseModel):
    name: str
    type: str
    enabled: bool
    status: str


class CapabilitySummaryResponse(BaseModel):
    tools: int
    mcp_servers: int
    ready: int
    degraded: int


class CapabilityCatalogResponse(BaseModel):
    tools: list[CapabilityToolResponse]
    mcp_servers: list[CapabilityMcpServerResponse]
    summary: CapabilitySummaryResponse


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000, examples=["什么是知识库？"])
    session_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
        description="会话 ID，用于延续历史对话",
    )


class ChatStreamRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, examples=["什么是知识库？"])
    session_id: str | None = Field(
        default=None, pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$",
        description="会话 ID，用于延续历史对话",
    )
    capability: str | None = Field(
        default=None, description="能力域过滤（第一阶段保留字段）"
    )


class ChatResumeRequest(BaseModel):
    session_id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]{0,127}$")
    decision: str | None = Field(default=None, pattern=r"^(approve|reject)$")
    message: str | None = Field(default=None, max_length=2000)
    decisions: list[str] | None = Field(
        default=None,
        min_length=1,
        description="按 interrupt 中 action 顺序提交 approve/reject 决策",
    )

    @model_validator(mode="after")
    def normalize_decisions(self):
        decisions = self.decisions or ([self.decision] if self.decision else [])
        if not decisions or any(item not in {"approve", "reject"} for item in decisions):
            raise ValueError("必须提供 decision 或 decisions，且只能是 approve/reject")
        self.decisions = decisions
        self.decision = decisions[0]
        return self


class ChatStreamSource(BaseModel):
    source: str
    chunk_id: str = ""
    excerpt: str | None = None
    hit_chain: list[str] = []


class CitationItem(BaseModel):
    source: str
    chunk_id: str
    excerpt: str | None = None


class ChatResponse(BaseModel):
    answer: str
    citations: list[CitationItem]
    conversation_id: str
    elapsed_ms: float


class SessionSummary(BaseModel):
    id: str
    title: str
    created: str
    turns: int
    size: int


class SessionListResponse(BaseModel):
    sessions: list[SessionSummary]


class SessionDetailResponse(BaseModel):
    id: str
    messages: list[dict]


class IndexRequest(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=1024,
        description="文件或目录路径",
        examples=["./data/external/docs"],
    )
    exclude: list[str] = Field(
        default_factory=list,
        description="添加目录时跳过这些相对子路径前缀（如 'manuals/Technology/HALCON'），用于不复制已存在内容的重复子树",
    )


class IndexTaskResponse(BaseModel):
    task_id: str
    status: str


class TaskStatusResponse(BaseModel):
    task_id: str
    status: str
    progress: str | None = None
    result: dict | None = None
    error: str | None = None


class UploadTasksResponse(BaseModel):
    tasks: list[IndexTaskResponse]
    saved: list[str]


class GraphStats(BaseModel):
    entities: int
    relations: int


class IndexTaskSummary(TaskStatusResponse):
    pass


class DiagnosticsTaskResponse(BaseModel):
    task_id: str
    status: str


class DiagnosticsCheck(BaseModel):
    name: str
    ok: bool
    status: str
    detail: str = ""
    error: str | None = None
    duration_ms: float | None = None
    fix: str = ""
    repairable: bool = False


class DiagnosticsSummary(BaseModel):
    total: int
    ok: int
    failed: int


class DiagnosticsResult(BaseModel):
    checks: list[DiagnosticsCheck]
    summary: DiagnosticsSummary


class DiagnosticsTaskStatus(BaseModel):
    task_id: str
    status: str
    result: DiagnosticsResult | None = None
    error: str | None = None


class RepairRequest(BaseModel):
    task_id: str
    name: str


class RepairResponse(BaseModel):
    name: str
    repaired: bool


class KnowledgeStatsResponse(BaseModel):
    documents: int
    chunks: int
    bm25_chunks: int | None = None
    graph: GraphStats
    index_task: IndexTaskSummary | None = None


class McpServerSummary(BaseModel):
    name: str
    type: str
    enabled: bool
    target: str


class SettingsResponse(BaseModel):
    knowledge_home: str
    data_dir: str
    external_dir: str
    chroma_persist_dir: str
    chroma_ok: bool
    graph_persist_dir: str
    embedding_model: str
    embedding_device: str
    llm_model: str
    llm_provider: str
    llm_api_base: str
    llm_api_configured: bool
    rerank_llm: str
    local_llm_base: str
    local_llm_model: str
    hf_endpoint: str
    hf_offline: bool
    graph_enabled: bool
    graph_llm_extraction: bool
    hybrid_search: bool
    grading: bool
    rewrite: bool
    context_compression: bool
    chunk_size: int
    chunk_overlap: int
    top_k: int
    max_context_tokens: int
    mcp_config_path: str
    mcp_enabled: bool
    jev_api_configured: bool
    mcp_servers: list[McpServerSummary]
    mcp_http_available: bool
    mcp_http_error: str | None
    lan_protection: bool
