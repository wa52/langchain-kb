# 02 — 增量 LLM 抽取

**What to build:** `update`/`add` 新增的文档自动走 LLM 抽取，合并到现有知识图谱，不重抽存量部分。增量场景下只对新增 chunk 调 LLM，合并实体和关系到已有图。

**Blocked by:** 01 — LLM 图谱抽取模块

**Status:** ready-for-agent

- [ ] `pipeline.py` 增量入口给新增 chunk 调用 LLM 抽取
- [ ] 合并逻辑：`(name,type)` 去重不覆盖；关系 `(source,target,relation)` 去重不覆盖
- [ ] `add` 一篇新文档 → `graph-search` 可查到其实体
