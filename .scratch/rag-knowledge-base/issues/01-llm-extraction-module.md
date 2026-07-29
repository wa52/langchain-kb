# 01 — LLM 图谱抽取模块

**What to build:** 新增 `ENABLE_GRAPH_LLM_EXTRACTION=true` 配置开关，实现 DeepSeek 批量抽取实体关系替代 jieba。用户运行 `build-graph` 后，知识图谱实体质量明显提升（噪声少、类型准确）。LLM 调用失败自动降级到 jieba，不中断流程。图文件原子写入，不会因中断产生半成品。

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `config.py` 新增 `ENABLE_GRAPH_LLM_EXTRACTION`（默认 false）和 `GRAPH_LLM_BATCH_SIZE`
- [ ] `src/graph_store/extraction_llm.py` 实现：分批调用 LLM、JSON 解析（含 ```json 包裹处理）、实体类型白名单校验、`(name,type)` 去重、异常时降级 jieba
- [ ] `src/graph_store/graph.py`：`build_from_chunks` 根据开关分支调 LLM 或 jieba；`save()` 改为 `.tmp` → `os.replace` 原子写入
- [ ] `src/graph_store/graph.py`：`build_graph_store()` 在 LLM 模式下创建 `ChatOpenAI` 实例传入
- [ ] `python main.py build-graph` 输出含 LLM 抽取提示，实体数 > 1000
