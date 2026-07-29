# 04 — 统一混合检索（含图谱）

**What to build:** `retrieve_knowledge` 工具内部同时查询向量库、BM25、知识图谱，对结果加权合并排序后返回。Agent 不再需要分别调 `retrieve_knowledge` 和 `retrieve_graph` 两个工具，一次调用拿到全量信息。图谱匹配度按「查询命中实体数 / 总实体数」计算评分。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `src/retrieval/retriever.py` 新增 `graph_relevance(query)` 评分函数
- [ ] `src/agent/tools.py`：`retrieve_knowledge` 内集成 graph 搜索，加权 fusion（w=0.5 可调）
- [ ] 返回格式包含合并后的 Top-K 结果，每项保留来源文件名
- [ ] 搜索 "RAG" 返回的结果同时包含向量匹配和图谱邻居信息
