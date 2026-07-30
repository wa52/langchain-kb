# BM25 Hybrid Search 接入 Spec

## Problem Statement

`ENABLE_HYBRID_SEARCH=true` 时，系统会在启动时通过 `rebuild_bm25()` 构建 BM25 关键词索引。但 `retrieve_knowledge` 工具实际检索时只调用了 `vector_store.similarity_search()`（纯向量搜索），没有使用 `EnsembleRetriever`（向量+BM25 加权）。BM25 索引建了但没用上。

## Solution

修改 `_search()` 函数（`tools.py`），用已有的 `get_retriever()`（`retriever.py`）替代直接调用 `vector_store.similarity_search()`。`get_retriever()` 在 `ENABLE_HYBRID_SEARCH=true` 且 BM25 索引就绪时自动返回 `EnsembleRetriever`，否则回退到纯向量检索。

## User Stories

1. As a 用户，I want 开启混合搜索后检索结果包含 BM25 关键词匹配的文档，so that 向量搜索找不到的精确关键词也能命中
2. As a 用户，I want 在 BM25 索引未构建时检索仍能正常回退到向量搜索，so that 启动和重建过渡期不会出错
3. As a 用户，I want CLI `search` 命令和 agent `retrieve_knowledge` 走同一套检索逻辑，so that 两种入口的搜索结果一致

## Implementation Decisions

### 改动文件

| 文件 | 改动 |
|------|------|
| `src/agent/tools.py` | `_search()` 改为调用 `get_retriever(k)`，移除 `vector_store` 参数 |
| `src/agent/tools.py` | `_grade()` 和 `retrieve_knowledge()` 中调用 `_search()` 时去掉 `vector_store` 参数 |
| `tests/test_retrieve_knowledge.py` | 新增 `test_hybrid_search_uses_ensemble` |

### 接口变更

```python
# BEFORE
def _search(query, vector_store, k):
    return vector_store.similarity_search(query, k=k)

# AFTER
def _search(query, k):
    from src.retrieval.retriever import get_retriever
    retriever = get_retriever(k=k)
    return retriever.invoke(query)
```

`get_retriever()` 已存在且行为正确：
- `ENABLE_HYBRID_SEARCH=true` + `_bm25_retriever` 非 `None` → `EnsembleRetriever([vector, bm25], weights=[0.5, 0.5])`
- 否则 → 纯 `vector_retriever` (MMR)

调用处变化：
- `retrieve_knowledge()`: `_search(query, vector_store, fetch_k)` → `_search(query, fetch_k)`
- `_grade()` 改写重试路径: `_search(new_query, vector_store, fetch_k)` → `_search(new_query, fetch_k)`

`get_vector_store()` 在 `get_retriever()` 内部通过单例获得，测试中 `set_vector_store()` 注入的 mock/in-memory store 会被正确使用。

### 依赖图

```
retrieve_knowledge → _search → get_retriever(k)
                                  ├─ ENABLE_HYBRID_SEARCH + _bm25_retriever → EnsembleRetriever
                                  └─ 否则 → Chroma.as_retriever(MMR)
```

## Testing Decisions

### 测试原则

- 只测外部行为（`retrieve_knowledge.invoke()` 返回的结果），不测内部实现细节
- 已有 seam：`test_retrieve_knowledge.py` 的 `TestRetrieveKnowledge` 类，使用真实 in-memory Chroma + 真实 embedding
- 优先使用最高 seam（集成测试），不新增低层单元测试

### 现有测试

```python
@PATCH_GRADING
@PATCH_REWRITE
@PATCH_COMPRESSION
class TestRetrieveKnowledge:
    def test_relevant_query(self): ...
    def test_empty_knowledge_base(self): ...
    def test_irrelevant_query(self): ...
```

### 新增测试

`test_hybrid_search_uses_ensemble`（在 `TestRetrieveKnowledge` 内）：

1. 向 Chroma 添加 `SAMPLE_DOCS`
2. 调用 `rebuild_bm25(store)` 构建 BM25 索引
3. 设置 `ENABLE_HYBRID_SEARCH=True`（patch `src.retrieval.retriever.ENABLE_HYBRID_SEARCH`）
4. 调用 `retrieve_knowledge.invoke({"query": "RAG"})`
5. 验证结果中包含 `rag_intro.md`

## Out of Scope

- 不改变 `get_retriever()` 的实现逻辑
- 不改变 CLI `search` 命令（已经正确使用 `get_retriever()`）
- 不改变 BM25 索引的构建和重建流程
- 不改变 grading/rewrite/compression 流程
- 不改变 `_compress` 和 `_grade` 的其他行为

## Further Notes

- `_search` 删除 `vector_store` 参数后，`retrieve_knowledge()` 内仍然保留 `get_vector_store()` 调用用于 grading/compression（它们需要直接的 document objects），不删除
- `get_retriever()` 内部通过 `get_vector_store(embeddings)` 获取 store，会触发单例，与工具中已有的 `get_vector_store()` 调用指向同一实例
- 当 `ENABLE_HYBRID_SEARCH` 为 False 时，`_search` 仍然通过 `get_retriever()` 返回纯向量检索，行为不变
