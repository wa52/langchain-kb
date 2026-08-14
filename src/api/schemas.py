from pydantic import BaseModel, Field


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


class ChatRequest(BaseModel):
    query: str = Field(min_length=1, max_length=4000, examples=["什么是知识库？"])
    session_id: str | None = Field(
        default=None, description="会话 ID，用于延续历史对话"
    )


class ChatStreamRequest(BaseModel):
    query: str = Field(min_length=1, max_length=2000, examples=["什么是知识库？"])
    session_id: str | None = Field(
        default=None, description="会话 ID，用于延续历史对话"
    )
    capability: str | None = Field(
        default=None, description="能力域过滤（第一阶段保留字段）"
    )


class ChatStreamSource(BaseModel):
    source: str
    chunk_id: str = ""
    excerpt: str | None = None


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
