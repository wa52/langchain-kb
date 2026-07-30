# MCP 暴露就绪检查报告

## 1. FastAPI-MCP 安装状态

| 项目 | 状态 |
|------|------|
| fastapi-mcp | **未安装** |
| 最新版本 | v0.4.0（2025-07-28 发布） |
| 当前 Python | 3.13.14（`>=3.10` 要求满足） |
| 兼容性 | ✅ 兼容（Python 3.10+，fastapi>=0.100.0） |

需要 `pip install fastapi-mcp` 后方可集成。

## 2. operation_id 检查

| 期望的 operationId | 当前值 | 备注 |
|-------------------|--------|------|
| `search_knowledge` | `search_documents` | **需要重命名** |
| `answer_with_knowledge` | `chat_completion` | **需要重命名** |
| `get_index_status` | `get_index_task_status` | **需要重命名** |

### 重复检查

当前 5 个 operationId 全部唯一，无重复：

```
health_check, search_documents, chat_completion, start_index_task, get_index_task_status
```

## 3. Schema 完整性

| Endpoint | Request Schema | Response Schema | 状态 |
|----------|---------------|-----------------|------|
| `POST /api/v1/retrieval/search` | `SearchRequest`（query, top_k） | `SearchResponse`（results[], elapsed_ms） | ✅ |
| `POST /api/v1/chat` | `ChatRequest`（query, session_id） | `ChatResponse`（answer, citations[], conversation_id, elapsed_ms） | ✅ |
| `GET /api/v1/index/tasks/{task_id}` | path param `task_id: str` | `TaskStatusResponse`（task_id, status, progress, result, error） | ✅ |

## 4. REST 调用验证

Phase 5 集成测试已验证三个接口均可独立通过 REST 调用成功：
- `search_knowledge` → 200 ✅
- `answer_with_knowledge` → 200 ✅（含真实 DeepSeek LLM 调用）
- `get_index_status` → 200 ✅

## 5. 风险清单

| 风险 | 等级 | 说明 |
|------|------|------|
| operationId 不匹配 | **高** | 三个 operationId 均需修改，否则 FastAPI-MCP 暴露的 tool 名称不是预期的 |
| `RmDep` 依赖生命周期 | **中** | `search_knowledge` 和 `get_index_status` 依赖 `RmDep`，ResourceManager 需通过 lifespan 提前初始化；FastAPI-MCP 的 ASGI 直连模式不会触发新的 HTTP 请求，依赖注入在 MCP 调用时正常工作，前提是 lifespan 已运行过 |
| `answer_with_knowledge` 无 `RmDep` | **低** | 该接口不依赖 `RmDep`，直接调用 `chat_with_rag()`（内部初始化 agent），独立可用 |
| 无认证机制 | **中** | 当前没有 auth 中间件，MCP 暴露后为完全公开调用；后续需参考 FastAPI-MCP 的 `Depends()` 认证方式添加 |
| `answer_with_knowledge` 调用 LLM 有成本 | **低** | 每次调用消耗 DeepSeek API 额度；MCP 客户端可能高频调用导致费用增加（已在现有的 `.env` 中控制） |
| 导入路径变化：`router.py` → `routers/` | **无** | Phase 5 已拆分完毕，不影响 FastAPI-MCP 挂载 |
| 异步索引任务 | **低** | 索引端点为异步（202），MCP 客户端可能需要轮询；只暴露 `get_index_status`（只读）无风险 |

## 6. 禁止暴露的接口映射

| 禁止项 | 对应路由 | 原因 |
|--------|---------|------|
| `index_document` | `POST /api/v1/documents/index` | 写操作，会修改知识库 |
| `delete_document` | 当前无此路由 | — |
| `reset_vector_store` | 当前无此路由 | — |
| `rebuild_all_indexes` | 当前无此路由（`/ingest` 为 console 命令） | — |
| `change_model_config` | 当前无此路由 | — |
| `execute_script` | 当前无此路由 | — |
| `health_check` | `GET /api/v1/health` | 对 Agent 无意义，不暴露 |

## 7. 具体修改计划

### Step 1 — 安装 FastAPI-MCP

```bash
pip install fastapi-mcp
```

### Step 2 — 重命名 operationId（3 处改动）

| 文件 | 改动 |
|------|------|
| `src/api/routers/search.py:14` | `operation_id="search_documents"` → `operation_id="search_knowledge"` |
| `src/api/routers/chat.py:23` | `operation_id="chat_completion"` → `operation_id="answer_with_knowledge"` |
| `src/api/routers/indexing.py:34` | `operation_id="get_index_task_status"` → `operation_id="get_index_status"` |

### Step 3 — 在 `src/api/app.py` 中添加 MCP 挂载

```python
from fastapi_mcp import FastApiMCP

def create_app() -> FastAPI:
    app = FastAPI(...)
    # ... include routers ...

    mcp = FastApiMCP(
        app,
        name="LangChain RAG Knowledge Base",
        description="提供知识库语义搜索、RAG 对话和索引状态查询的 MCP 接口",
    )
    mcp.mount()

    return app
```

### Step 4 — 限制只暴露三个工具

FastAPI-MCP v0.4.0 支持通过 FastAPI 的 `Depends()` 做权限控制，或通过 `describe` 参数做选择性暴露。推荐方式：

```python
mcp = FastApiMCP(
    app,
    describe=False,           # 不自动暴露所有接口
)
# 只显式注册三个允许的工具
mcp.add_tool_by_operation_id("search_knowledge")
mcp.add_tool_by_operation_id("answer_with_knowledge")
mcp.add_tool_by_operation_id("get_index_status")
```

或使用全局排除模式：

```python
mcp = FastApiMCP(
    app,
    exclude_operations=[
        "health_check",
        "start_index_task",
    ],
)
```

### Step 5 — 更新测试断言

`tests/test_api_routes.py` 中 operationId 不直接在测试中引用（目前通过路由 path 测试），无需修改。

但若新增 MCP 相关的集成测试，应验证三个 tool 的名称正确。

### Step 6 — 验证

```bash
pip install fastapi-mcp
python -m pytest tests/ -q --ignore=tests/test_full_workflow.py
# 手动验证 MCP 端点
python -c "
from src.api.app import app
from fastapi.testclient import TestClient
client = TestClient(app)
# MCP 默认挂载在 /mcp
resp = client.post('/mcp', json={'jsonrpc': '2.0', 'method': 'tools/list', 'id': 1})
print(resp.json())
"
```
