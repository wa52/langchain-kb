# OpenCode MCP 知识库验收报告

## 测试环境

- **MCP 端点**: `http://127.0.0.1:8000/mcp`
- **传输协议**: Streamable HTTP（JSON-RPC 2.0）
- **服务状态**: 运行中

---

## 测试一：工具发现

**结果**: ✅ 成功

3 个工具全部发现，参数完整：

| 工具名 | 参数 | 说明 |
|--------|------|------|
| `search_knowledge` | `query` (string, required), `top_k` (integer, default=5) | 语义搜索知识库，返回 chunk_id、content、source、score |
| `answer_with_knowledge` | `query` (string, required), `session_id` (string, optional) | RAG 对话，返回 answer、citations、conversation_id |
| `get_index_status` | `task_id` (string, required) | 查询索引任务状态，返回 task_id、status、progress、result、error |

---

## 测试二：知识检索

**结果**: ✅ 成功

调用 `search_knowledge(query="FastAPI lifespan 为什么适合管理 Embedding 和向量数据库生命周期", top_k=5)` 返回 5 个结果：

| chunk_id | source | score | content 摘要 |
|----------|--------|-------|--------------|
| `8dc19f24-...` | 文档 PDF | 0.41 | HALCON 线性算法相关描述 |
| `f3e7c6d1-...` | 文档 PDF | 0.41 | HALCON 线性算法相关描述 |
| `4b3b5e5e-...` | 文档 PDF | 0.38 | 视差计算方法对比（fast vs accurate）|
| `17f49626-...` | 文档 PDF | 0.38 | 视差计算方法对比 |
| `b34b0bd8-...` | 文档 PDF | 0.37 | 3D Metrology 模块文档 |

**说明**: 当前向量库以 HALCON 技术文档为主，不包含项目自身架构文档，因此检索结果相关性较低（0.37-0.41）。`elapsed_ms: 452.58ms`。

---

## 测试三：知识问答

**结果**: ✅ 成功

调用 `answer_with_knowledge(query="为什么对话请求不应该重新执行文档切片和向量化")` 返回：

| 字段 | 值 |
|------|-----|
| `answer` | LLM 生成的回答（中文）|
| `citations` | `[]`（无引用）|
| `conversation_id` | `session_20260731_053746` |
| `elapsed_ms` | 17446.02（含 DeepSeek API 调用）|

**说明**: 回答已生成但未引用具体文档片段，因为向量库中未检索到与 Embedding/向量库生命周期管理直接相关的内容。MCP 正确调用了现有的 RAG Agent 流程，未出现重复初始化。

---

## 测试四：索引状态

**结果**: ✅ 成功

创建任务后调用 `get_index_status(task_id="5f099b65-1029-47fd-ab2d-726542dc795b")` 返回：

```json
{
  "task_id": "5f099b65-1029-47fd-ab2d-726542dc795b",
  "status": "running",
  "progress": "Indexing...",
  "result": null,
  "error": null
}
```

任务存在时正常返回；不存在时返回 404 错误（未伪造数据）。

---

## 综合评价

| 项目 | 结果 |
|------|------|
| MCP 连接成功 | ✅ |
| 工具发现成功 | ✅ 3/3 |
| `search_knowledge` 调用成功 | ✅ |
| `answer_with_knowledge` 调用成功 | ✅ |
| `get_index_status` 调用成功 | ✅ |
| 返回数据符合 Schema | ✅ 所有字段类型正确 |
| 重复初始化 | ✅ 未出现（共享 ResourceManager 单例）|

## 剩余问题

1. **向量库未包含项目自有文档**：当前 ChromaDB 仅有 HALCON 技术文档，没有项目架构/经验库内容。需要执行 `ingest` 命令导入项目文档后，搜索和问答结果会更加相关。
2. **GBK 终端中文显示问题**：PowerShell 输出中文字符被截断或乱码，但数据本身（JSON）正确。这是终端编码问题，非 MCP 服务问题。
3. **无有效索引任务时测试不便**：需要通过 REST API 先创建任务才能测试 `get_index_status`，MCP 本身不提供任务创建能力（安全设计）。
