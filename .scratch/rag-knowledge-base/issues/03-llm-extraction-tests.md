# 03 — LLM 抽取测试

**What to build:** Mock LLM 响应的测试套件，覆盖正常 JSON 抽取、LLM 异常降级 jieba、带 ```json 包裹的乱码 JSON 三种场景。

**Blocked by:** 01 — LLM 图谱抽取模块

**Status:** ready-for-agent

- [ ] Mock LLM 返回合法 JSON → 验证实体和关系被正确添加到图
- [ ] Mock LLM 抛出异常 → 验证降级到 jieba 后图不空且实体数 > 0
- [ ] Mock LLM 返回 ```json\n{...}\n``` 格式 → 验证正则提取成功
- [ ] `pytest tests/` 全部通过
