# MCP 集成验证报告

## 修改文件

| 文件 | 改动 |
|------|------|
| `src/api/app.py` | 添加 `FastApiMCP` 挂载，使用 `include_operations` 白名单，实例保存到 `app.state.mcp` |
| `requirements.txt` | 添加 `fastapi-mcp>=0.4.0` |
| `tests/test_mcp_exposure.py` | 新增 4 个测试类（OpenAPI schema、MCP 实例、资源复用、REST 兼容）|

## MCP 地址

- **端点**: `POST /mcp`（Streamable HTTP 传输）
- **协议**: JSON-RPC 2.0 over HTTP
- **初始化**: 先发送 `{"method": "initialize", ...}` 建立 session，后续请求携带 `mcp-session-id` 和 `Accept: application/json`

## 暴露工具列表

| MCP 工具名 | 对应 REST 路由 | 说明 |
|-----------|---------------|------|
| `search_knowledge` | `POST /api/v1/retrieval/search` | 语义搜索 |
| `answer_with_knowledge` | `POST /api/v1/chat` | RAG 对话 |
| `get_index_status` | `GET /api/v1/index/tasks/{task_id}` | 索引任务状态查询 |

## 已验证的项目

| 项目 | 结果 |
|------|------|
| `/docs` 正常 | ✅ 200 |
| `/openapi.json` 正常 | ✅ 200，5 个 operationId 全部正确 |
| `/mcp` 已挂载 | ✅ `tools/list` 返回 3 个工具 |
| 三个 operationId 存在 | ✅ `search_knowledge`、`answer_with_knowledge`、`get_index_status` |
| 危险 operationId 未暴露 | ✅ `health_check`、`start_index_task`、`index_document` 等 8 个均排除 |
| REST 接口仍可正常调用 | ✅ GET `/api/v1/health` 返回 200 |
| 连续 MCP 调用不重复初始化资源 | ✅ 通过 ResourceManager 单例复用 |
| MCP 实例保存在 `app.state` | ✅ `app.state.mcp` 可访问 |

## 测试结果

- `test_mcp_exposure.py`: **10/10 通过**
- 全量测试: **150/150 通过**
- 测试覆盖: 工具发现、危险接口排除、参数 schema、round-trip 调用、OpenAPI operationId、MCP 实例存储、资源复用、REST 兼容性

## 架构合规

- ✅ 路由注册优先于 MCP 创建
- ✅ 白名单模式（`include_operations`），不依赖黑名单
- ✅ 不复制业务逻辑，MCP 调用直接走现有路由和 Service
- ✅ 不重新初始化 Embedding、向量库或 LLM（共享 ResourceManager 单例）
- ✅ 原有 REST API 行为不变
