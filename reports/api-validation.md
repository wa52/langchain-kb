# API v1 验证报告

## 端点清单

| Method | Path | Status | 说明 |
|--------|------|--------|------|
| GET | `/api/v1/health` | 200 | 健康检查 |
| POST | `/api/v1/retrieval/search` | 200 | 语义搜索 |
| POST | `/api/v1/chat` | 200 | RAG 对话 |
| POST | `/api/v1/documents/index` | 202 | 异步索引 |
| GET | `/api/v1/index/tasks/{task_id}` | 200 | 任务轮询 |

## 错误码

| Status | 场景 |
|--------|------|
| 400 | 索引路径不存在或非法 |
| 404 | 任务 ID 不存在、路由不存在 |
| 409 | 同一路径正在索引中 |
| 422 | 请求参数校验失败 |
| 500 | 内部错误 |
| 503 | ResourceManager 未就绪 |

## 验证结果

- 所有端点返回正确状态码
- `/openapi.json` 生成 5 个 path，含完整 Request/Response schema
- `/docs` Swagger UI 正常渲染
- 无重复 `operationId`
- 422 错误统一格式 `{"error": ..., "detail": ...}`
- 404 未匹配路由返回统一 JSON 而非 HTML
- `ChatResponse` 包含 `conversation_id`（兼容字段 `session_id` → `conversation_id`）和 `citations` 数组
- `SearchRequest.query` 限制 `max_length=2000`，`top_k` 限制 `[1, 50]`
- 索引端点返回 `202 Accepted` + `task_id`

## 架构合规

- 路由文件按 domain 拆分：`health.py`、`search.py`、`chat.py`、`indexing.py`
- 路由只做参数校验（Pydantic）和调用 service 层，无直接 DB/LLM/文件 I/O
- 共享 `RmDep` 依赖放 `dependencies.py`
- 异步索引通过 `asyncio.create_task` + `run_in_executor` 实现

## 测试覆盖

- `tests/test_api_routes.py` — 16 个测试覆盖所有端点及边界
- 全量 140 个测试通过
