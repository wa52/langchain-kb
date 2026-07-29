# 05 — Agent 输出来源引用

**What to build:** Agent 回答末尾自动附上去源文件引用 `[来源: file1.md, file2.md]`。每个引用的来源文件在 Answer 中首次出现时标出。System prompt 明确要求 Agent 在回答中引用来源。

**Blocked by:** 04 — 统一混合检索（含图谱）

**Status:** ready-for-agent

- [ ] `retrieve_knowledge` 输出末尾追加 `[来源: file1.md, file2.md]`
- [ ] Agent system prompt 增加引用指令
- [ ] Chat 提问后输出末尾出现 `[来源: ...]`
