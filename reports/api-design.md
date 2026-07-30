# API 设计文档 v1 — LangChain RAG 知识库系统

> 本文档定义第一版 FastAPI 接口合同。设计基于 `IngestionService`（`src/ingestion/pipeline.py`）、`RetrievalService`（`src/vector_store/service.py` + `src/api/services/search.py`）和 `ChatService`（`src/api/services/chat.py`）。
>
> **路由职责**：只做参数校验 + 调用 Service。不直接操作向量库、LLM 或文件系统。
>
> **前缀**：所有路由挂载在 `/api/v1` 下。

---

## 1. GET /health

| 元字段 | 值 |
|--------|-----|
| Path | `/api/v1/health` |
| Method | `GET` |
| operation_id | `health_check` |
| summary | 健康检查 |
| description | 返回系统运行状态，包含启动时间、索引版本号、向量库文档数和知识图谱实体数。**不得触发模型重新初始化。** |
| 调用 Service | `src.api.services.health.get_health_status(rm)` |
| 暴露给 MCP | ✅ 是（MCP 连接前需要检查服务可用性） |

### 请求

**Query 参数（无）**

### 响应

**200 OK**

```json
{
  "status": "ok",
  "uptime": 12345.67,
  "index_version": 3,
  "vector_count": 1520,
  "entity_count": 3167
}
```

| 字段 | 类型 | 必填 | 默认值 | 说明 |
|------|------|------|--------|------|
| `status` | `string` | ✅ | — | 固定为 `"ok"`；如果 ResourceManager 未就绪返回 503 |
| `uptime` | `float` | ✅ | — | 服务启动至今的秒数，保留 2 位小数 |
| `index_version` | `int` | ✅ | `0` | 索引版本号，每次 invalidate_retriever_cache 递增 |
| `vector_count` | `int` | ✅ | `0` | Chroma 集合中文档总数 |
| `entity_count` | `int` | ✅ | `0` | 知识图谱中的实体（节点）数 |

### 错误响应

| 状态码 | 条件 | body |
|--------|------|------|
| 503 | ResourceManager 未初始化或 startup 失败 | `{"error": "Service Unavailable", "detail": "ResourceManager not ready"}` |

---

## 2. POST /api/v1/retrieval/search

| 元字段 | 值 |
|--------|-----|
| Path | `/api/v1/retrieval/search` |
| Method | `POST` |
| operation_id | `search_documents` |
| summary | 搜索知识库 |
| description | 在向量库中执行语义搜索，返回相关文档片段。结果必须包含 chunk_id、content、source、score。 |
| 调用 Service | `src.api.services.search.search_documents(rm, query, top_k)` |
| 暴露给 MCP | ✅ 是（外部工具可直接调用搜索） |

### 请求

**Request Body**

```json
{
  "query": "什么是 LangChain？",
  "top_k": 5
}
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
|------|------|------|--------|---------|------|
| `query` | `string` | ✅ | — | `min_length=1`, `max_length=2000` | 搜索查询文本 |
| `top_k` | `integer` | ❌ | `5` | `1 ≤ top_k ≤ 50` | 返回结果数量上限 |

### 响应

**200 OK**

```json
{
  "results": [
    {
      "chunk_id": "c3f7a2b1...",
      "content": "LangChain 是一个用于构建 LLM 应用的开源框架...",
      "source": "langchain_intro.md",
      "score": 0.8921
    }
  ],
  "elapsed_ms": 134.56
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `results` | `array[SearchResultItem]` | ✅ | 搜索结果列表，按相似度降序 |
| `elapsed_ms` | `float` | ✅ | 搜索耗时（毫秒），保留 2 位小数 |

**SearchResultItem**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `chunk_id` | `string` | ✅ | 文档片段唯一标识 |
| `content` | `string` | ✅ | 文档片段正文（截断至 500 字符） |
| `source` | `string` | ✅ | 来源文件名 |
| `score` | `float` | ✅ | 相关性分数，保留 4 位小数 |

### 错误响应

| 状态码 | 条件 | body |
|--------|------|------|
| 422 | `query` 为空 | `{"error": "Validation Error", "detail": "query: String should have at least 1 character"}` |
| 422 | `top_k` 超出范围 | `{"error": "Validation Error", "detail": "top_k: Input should be less than or equal to 50"}` |
| 503 | ResourceManager 未就绪 | `{"error": "Service Unavailable", "detail": "ResourceManager not ready"}` |
| 500 | 搜索过程内部异常 | `{"error": "Internal server error", "detail": "<异常信息>"}` |

---

## 3. POST /api/v1/chat

| 元字段 | 值 |
|--------|-----|
| Path | `/api/v1/chat` |
| Method | `POST` |
| operation_id | `chat_completion` |
| summary | 与 RAG 助手对话 |
| description | 发送用户消息给 RAG Agent，Agent 使用检索增强生成返回答案。支持会话历史延续。每次请求独立，失败不影响后续请求。 |
| 调用 Service | `src.api.services.chat.chat_with_rag(query, session_id)` |
| 暴露给 MCP | ✅ 是（作为 MCP 的 chat 工具暴露） |

### 请求

**Request Body**

```json
{
  "query": "LangChain 有哪些核心模块？",
  "session_id": null
}
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
|------|------|------|--------|---------|------|
| `query` | `string` | ✅ | — | `min_length=1`, `max_length=4000` | 用户输入的消息文本 |
| `session_id` | `string` | ❌ | `null` | — | 会话标识；传 `null` 或不传则新建会话 |

### 响应

**200 OK**

```json
{
  "answer": "LangChain 的核心模块包括：Model I/O、Retrieval、Chains、Agents、Memory、Callbacks。[来源: langchain_intro.md]",
  "citations": [
    {
      "source": "langchain_intro.md",
      "chunk_id": "a1b2c3d4...",
      "excerpt": "## 核心模块\n\n1. **Model I/O**：处理与 LLM 的输入输出交互..."
    }
  ],
  "conversation_id": "session_20260730_233000",
  "elapsed_ms": 3250.42
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `answer` | `string` | ✅ | Agent 生成的回答文本 |
| `citations` | `array[CitationItem]` | ✅ | 回答中引用的来源列表（**可能为空**） |
| `conversation_id` | `string` | ✅ | 会话 ID，用于后续对话延续 |
| `elapsed_ms` | `float` | ✅ | 总耗时（毫秒），保留 2 位小数 |

**CitationItem**

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `source` | `string` | ✅ | 来源文件名 |
| `chunk_id` | `string` | ✅ | 对应的文档片段 ID |
| `excerpt` | `string` | ❌ | 来源文本摘录（可选，最多 300 字符） |

### 错误响应

| 状态码 | 条件 | body |
|--------|------|------|
| 422 | `query` 为空 | `{"error": "Validation Error", "detail": "query: String should have at least 1 character"}` |
| 500 | Agent 执行过程异常 | `{"error": "Internal server error", "detail": "<异常信息>"}` |

> **注意**：chat 不依赖 ResourceManager 的 ready 状态（Agent 自身管理 LLM 和检索器生命周期），因此不会返回 503。

### 设计决策

- `citations` 字段从 Agent 的 `retrieve_knowledge` 工具调用结果中提取，而非事后解析 `answer` 字符串。
- `conversation_id` 替换 `session_id`，语义更清晰：标识一段对话而非一个浏览器 session。
- 一个请求失败不影响后续请求——每个请求创建独立的 Agent 实例（当前实现如此）。

---

## 4. POST /api/v1/documents/index

| 元字段 | 值 |
|--------|-----|
| Path | `/api/v1/documents/index` |
| Method | `POST` |
| operation_id | `start_index_task` |
| summary | 启动文档索引任务 |
| description | 将文件或目录添加到知识库并启动异步索引。立即返回 task_id，不等待索引完成。同一路径不可同时进行两个索引任务。 |
| 调用 Service | `src.api.services.indexing.get_task_manager()` + `run_index_task()` |
| 暴露给 MCP | ❌ 否（索引是内部管理操作，MCP 只需读取结果） |

### 请求

**Request Body**

```json
{
  "path": "./data/external/docs"
}
```

| 字段 | 类型 | 必填 | 默认值 | 校验规则 | 说明 |
|------|------|------|--------|---------|------|
| `path` | `string` | ✅ | — | `min_length=1`, `max_length=1024` | 要索引的文件或目录路径（相对于工作目录或绝对路径） |

> **校验规则**：路径不得包含 `..` 遍历；路径必须是已存在的文件或目录。若路径不存在，返回 400。

### 响应

**202 Accepted**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "pending"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | UUID v4 格式的任务标识 |
| `status` | `string` | ✅ | 初始状态 `"pending"` |

**状态码**：`202 Accepted`（非 200），以明确标识这是异步操作。

### 错误响应

| 状态码 | 条件 | body |
|--------|------|------|
| 400 | `path` 不存在 | `{"error": "Bad Request", "detail": "Path not found: <path>"}` |
| 400 | `path` 包含 `..` | `{"error": "Bad Request", "detail": "Path must not contain '..'"}` |
| 409 | 同一 `path` 已有进行中的任务 | `{"error": "Conflict", "detail": "Already indexing: <path>"}` |
| 422 | `path` 为空 | `{"error": "Validation Error", "detail": "path: String should have at least 1 character"}` |
| 503 | ResourceManager 未就绪 | `{"error": "Service Unavailable", "detail": "ResourceManager not ready"}` |

---

## 5. GET /api/v1/index/tasks/{task_id}

| 元字段 | 值 |
|--------|-----|
| Path | `/api/v1/index/tasks/{task_id}` |
| Method | `GET` |
| operation_id | `get_index_task_status` |
| summary | 查询索引任务状态 |
| description | 轮询异步索引任务的当前状态。任务可能处于 `pending` → `running` → `done` / `failed`。 |
| 调用 Service | `src.api.services.indexing.get_task_manager().get_task(task_id)` |
| 暴露给 MCP | ❌ 否（内部任务状态查询，MCP 无直接用例） |

### 请求

**Path 参数**

| 参数 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | UUID v4 格式的任务标识 |

### 响应

**200 OK**

```json
{
  "task_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "running",
  "progress": "Indexing...",
  "result": null,
  "error": null
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `task_id` | `string` | ✅ | 任务标识 |
| `status` | `string` | ✅ | `"pending"` \| `"running"` \| `"done"` \| `"failed"` |
| `progress` | `string` | ❌ | 进度描述文本 |
| `result` | `object` | ❌ | 完成结果：`{"chunks_added": <int>}`（仅 `done` 状态时存在） |
| `error` | `string` | ❌ | 错误信息（仅 `failed` 状态时存在） |

**状态机：**

```
pending ──→ running ──→ done
                       └─→ failed
```

### 错误响应

| 状态码 | 条件 | body |
|--------|------|------|
| 404 | `task_id` 不存在 | `{"error": "Not Found", "detail": "Task not found: <task_id>"}` |

---

## 路由与 Service 对应表

| API | 路由 | Service 文件 | 调用函数 |
|-----|------|-------------|---------|
| 健康检查 | `GET /api/v1/health` | `src/api/services/health.py` | `get_health_status(rm)` |
| 搜索 | `POST /api/v1/retrieval/search` | `src/api/services/search.py` | `search_documents(rm, query, top_k)` |
| 对话 | `POST /api/v1/chat` | `src/api/services/chat.py` | `chat_with_rag(query, session_id)` |
| 索引 | `POST /api/v1/documents/index` | `src/api/services/indexing.py` | `get_task_manager().create_task(path)` + `run_index_task(task_id, path)` |
| 任务查询 | `GET /api/v1/index/tasks/{task_id}` | `src/api/services/indexing.py` | `get_task_manager().get_task(task_id)` |

---

## MCP 暴露建议

| 操作 | 是否暴露 | 原因 |
|------|---------|------|
| `health_check` | ✅ 暴露 | MCP 连接前需要验证服务可用性 |
| `search_documents` | ✅ 暴露 | 外部工具可直接调用知识库搜索，是 MCP 的典型用例 |
| `chat_completion` | ✅ 暴露 | 作为 MCP 的 chat 工具，是最核心的交互入口 |
| `start_index_task` | ❌ 不暴露 | 索引是内部管理操作，不应由 MCP 触发 |
| `get_index_task_status` | ❌ 不暴露 | 内部任务状态，与 MCP 无直接关系 |

---

## 统一错误结构

所有错误响应使用同一 Schema：

```json
{
  "error": "Not Found",
  "detail": "Route POST /api/v1/chat not found"
}
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `error` | `string` | ✅ | 错误类型短语（如 `"Not Found"`、`"Validation Error"`） |
| `detail` | `string` | ❌ | 详细错误描述，可为 `null` |

实现的错误状态码覆盖：

| 状态码 | 含义 | 适用接口 |
|--------|------|---------|
| 200 | 成功 | 所有 |
| 202 | 已接受（异步） | `POST /documents/index` |
| 400 | 请求错误 | `POST /documents/index` |
| 404 | 资源不存在 | `GET /index/tasks/{task_id}`、未匹配路由 |
| 409 | 冲突 | `POST /documents/index` |
| 422 | 参数校验失败 | `POST /retrieval/search`、`POST /chat`、`POST /documents/index` |
| 500 | 服务器内部错误 | 所有 |
| 503 | 服务不可用 | `GET /health`、`POST /retrieval/search`、`POST /documents/index` |

---

## 与当前实现的差异（v1 合同变更点）

| 当前实现 | v1 合同 |
|---------|---------|
| `SearchResponse` 无 `elapsed_ms` 返回（但已实现） | 保留 |
| `ChatRequest` 字段名为 `session_id` | 改为 `conversation_id`（语义更清晰） |
| `ChatResponse` 无 `citations` 字段 | 新增 `citations: array[CitationItem]` |
| `POST /documents/index` 返回 200 | 改为 202 Accepted |
| 无 `conversation_id` | 新增（替换原 `session_id` 返回字段名） |
| `top_k` 无显式 `max_length` | 新增 `max_length=2000` 校验 |

---

## 未包含的接口（明确排除）

- **删除接口** — 不设计 `DELETE /documents/{source}`，因为 v1 聚焦写入和读取
- **重置数据库** — 不设计 `POST /reset`，因为破坏性操作需要审批流程
- **任意代码执行** — 不设计 `POST /execute` 或 `POST /eval`
- **用户管理** — 不设计认证/授权接口，v1 无用户概念
- **文件列表** — 不设计 `GET /files`，属于管理功能而非 RAG 核心
- **配置热更新** — 不设计 `PATCH /config`，v1 配置通过 .env 文件管理

---

*设计版本：v1.0 • 日期：2026-07-30*
