# 个人知识库 · 工业视觉 AI 工程师

基于 RAG 的个人知识库系统，以 **AI 能力** 为核心组织知识（而非按工具分类），
目标是让 AI 能独立完成一个工业视觉项目：需求分析 → 知识研究 → 方案设计 →
算法实现 → 工程开发 → 项目验证。

## 核心特性

- **RAG 问答**：混合检索（向量 + BM25）→ LLM 评分过滤 → 上下文压缩 → 知识图谱关联
- **工业视觉能力模型**：7 大能力域组织知识（需求分析/知识研究/方案设计/算法实现/工程开发/项目验证/能力评估）
- **能力导向检索**：`knowledge search "xxx" --capability 4` 按能力域过滤
- **项目方案生成器**：`knowledge design "PCB缺陷检测"` 一键生成结构化工业视觉方案
- **外部 MCP 集成**：agent 可调用外部 MCP server 工具（如 filesystem），每个 server 收敛为一个工具入口
- **Web 界面**：左侧历史会话 + 右侧对话，自动滚动
- **多端入口**：CLI / Web / API / MCP

## 安装

```bash
pip install -r requirements.txt
pip install -e .          # 安装 knowledge 命令
```

配置 `.env`（参考 `.env.example`）：

```ini
DEEPSEEK_API_KEY=你的key
HF_ENDPOINT=https://huggingface.co
```

## 使用

```bash
knowledge web                  # Web 界面（http://127.0.0.1:8000）
knowledge cli                  # 交互式控制台
knowledge chat "问题"          # 单次问答
knowledge index <路径>         # 索引文档（.md/.txt/.pdf/.hdev/代码）
knowledge search "词" --capability 4   # 能力域检索
knowledge map                  # 查看能力模型与知识覆盖
knowledge design "PCB缺陷检测" # 生成工业视觉方案（输出 data/projects/）
knowledge doctor               # 健康检查
```

## 外部 MCP 集成

在 `<KNOWLEDGE_HOME>/mcp.json` 配置外部 MCP server（格式参考 `knowledge/mcp.example.json`）：

```json
{
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/data"],
      "enabled": true
    }
  }
}
```

每个 MCP server 在 agent 工具集中收敛为一个工具（如 `filesystem`），
其下所有操作通过 `operation` 参数调用。加新 server 只需编辑 `mcp.json`。

## 项目结构

```
src/
├── agent/          # RAG agent、工具、项目工作流、方案生成、外部 MCP 客户端
├── api/            # FastAPI 服务、Web 界面、MCP 暴露
├── capability/     # 能力模型定义与映射
├── cli/            # knowledge 命令
├── graph_store/    # 知识图谱（jieba/LLM 实体抽取）
├── ingestion/      # 文档加载、切分、知识化、向量化
├── llm/            # LLM 客户端（DeepSeek / Ollama）
├── retrieval/      # 混合检索、评分、查询重写
└── vector_store/   # Chroma 向量库
```

## 测试

```bash
python -m pytest tests/
```

## 文档

- `docs/global-usage.md` — 全局命令使用
- `docs/deployment.md` — 打包部署
- `docs/knowledge-cli.md` — CLI 设计
- `reports/` — 架构与性能报告

## 说明

- 数据目录通过 `KNOWLEDGE_HOME` 环境变量指定（默认项目根）
- 首次运行自动创建目录骨架并下载 embedding 模型
