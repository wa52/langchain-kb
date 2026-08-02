# Personal Knowledge Base · 个人知识库

> 面向 **工业视觉 AI 工程师** 的智能知识库系统。
> 以 **AI 能力** 为核心组织知识，让 AI 能独立完成一个工业视觉项目：
> 需求分析 → 知识研究 → 方案设计 → 算法实现 → 工程开发 → 项目验证。

<div align="center">

![Python](https://img.shields.io/badge/Python-3.10%2B-blue)
![RAG](https://img.shields.io/badge/RAG-Hybrid%20%2B%20BM25-green)
![MCP](https://img.shields.io/badge/MCP-Client%20%2B%20Server-orange)
![License](https://img.shields.io/badge/License-MIT-yellow)

</div>

---

## ✨ 核心特性

### 🧠 工业视觉 AI 能力模型
知识按 **AI 能力** 组织（而非按工具分类），7 大能力域：

| ID | 能力域 | 说明 |
|----|--------|------|
| 1 | 需求分析 | 检测目标识别、技术指标提取、可行性评估 |
| 2 | 知识研究 | 知识检索、跨来源综合、技术选型调研 |
| 3 | 方案设计 | 成像系统、光学计算、算法方案、系统架构 |
| 4 | 算法实现 | 预处理/分割/定位/缺陷/测量/OCR/深度学习/3D |
| 5 | 工程开发 | 视觉程序、SDK 集成、PLC/机器人通讯、部署 |
| 6 | 项目验证 | 现场调试、鲁棒性、性能优化、验收 |
| 7 | 能力评估 | 方案评估、算法对比、持续优化 |

每份知识映射到 AI 的 **能力**，来源（HALCON/OpenCV/LangChain...）只是辅助维度。

### 🚀 RAG 问答
- **混合检索**：向量（Chroma MMR）+ BM25，Ensemble 融合
- **LLM 评分过滤**：并行判断文档相关性，全不相关自动查询重写
- **上下文压缩**：LLM 并行摘要，保留关键事实
- **知识图谱**：实体/关系关联增强（jieba / LLM 双模式）

### 🏭 工业视觉方案生成器
`knowledge design "PCB缺陷检测"` —— 一句话需求 → 结构化方案：

```
data/projects/PCB缺陷检测/
├── requirement.md   # 需求分析
├── solution.md      # 10 节方案（成像/定位/算法/软件/风险）
├── algorithm.md     # 算法推荐（规则表 + LLM 算子细化）
├── risk.md          # 风险分析
└── questions.md     # 待确认问题
```

### 🔌 外部 MCP 集成
Agent 可调用外部 MCP server 工具，每个 server 收敛为 **1 个工具入口**：

```
retrieve_knowledge   ← 本地知识检索
project_workflow     ← 本地项目引导
filesystem           ← 外部 MCP（含 read_file / write_file / list_directory 等操作）
```

添加新 MCP server 只需编辑 `mcp.json`，无需改代码。

### 🌐 多端入口
| 入口 | 说明 |
|------|------|
| `knowledge web` | Web 界面（聊天 + 历史会话）|
| `knowledge cli` | 交互式控制台 |
| `knowledge chat` | 单次问答 |
| `knowledge search` | 能力域检索 |
| API + MCP Server | `/api/v1` + `/mcp`（3 个工具暴露）|

---

## 📦 安装

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 安装 CLI（可选，全局 knowledge 命令）
pip install -e .

# 3. 配置 .env
cp .env.example .env
# 编辑 .env：填入 DEEPSEEK_API_KEY
```

> Python ≥ 3.10。首次运行自动下载 embedding 模型（bge-small-zh-v1.5，约 33MB）。

### .env 配置

```ini
# DeepSeek API（必填，问答/方案生成/评分用）
DEEPSEEK_API_KEY=your_deepseek_api_key
DEEPSEEK_API_BASE=https://api.deepseek.com

# Embedding 模型: bge-small-zh(推荐) / bge-m3 / bge-base-zh / openai
EMBEDDING_MODEL=bge-small-zh

# HuggingFace 端点（国内网络走代理时保持官方源）
HF_ENDPOINT=https://huggingface.co

# 分块参数
CHUNK_SIZE=500
CHUNK_OVERLAP=80

# 检索参数
TOP_K=5
```

---

## 📥 克隆后使用（从 GitHub 拉取）

克隆项目后，**运行时所需的资料/配置不会包含在仓库中**（`.env`、`data/`、
`chroma_db/` 等均在 `.gitignore` 排除）。按下面清单配置后即可使用：

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 创建配置（.env 仓库中不提供，只提供模板）
cp .env.example .env
# 编辑 .env，填入 DEEPSEEK_API_KEY（必填）

# 3. 验证配置与依赖
python main.py knowledge doctor

# 4. 导入你自己的资料（支持 .md/.txt/.pdf/.hdev/源代码）
python main.py knowledge index ./你的资料路径

# 5. 启动
python main.py knowledge web        # 或 knowledge web（安装 CLI 后）
```

**克隆后首次运行会自动：**
- 创建 `data/`、`chroma_db/` 目录骨架
- 下载 embedding 模型（bge-small-zh-v1.5，约 33MB，需联网）

**可选配置：**
- **外部 MCP**：`cp knowledge/mcp.example.json mcp.json`，编辑填入你的目录
- **离线环境**：提前下载模型 `hf download BAAI/bge-small-zh-v1.5`，或设置 `HF_HUB_OFFLINE=1`
- **路径含中文**：在 `.env` 设置 ASCII 的 `CHROMA_PERSIST_DIR`

> 若想直接使用已有知识库（含历史导入的 11 万 chunks），需同时拷贝本地的
> `data/` 和 `chroma_db/` 目录，否则克隆后知识库为空，需重新 `index`。

---

## 🚀 快速开始

```bash
# 1. 索引你的文档（支持 .md/.txt/.pdf/.hdev/源代码）
knowledge index ./docs

# 2. 启动 Web 界面
knowledge web          # 访问 http://127.0.0.1:8000

# 3. 问答
knowledge chat "什么是RAG？"

# 4. 生成工业视觉方案
knowledge design "设计一个PCB缺陷检测系统"

# 5. 查看能力模型
knowledge map
```

---

## 📖 命令参考

```bash
knowledge web [--host 0.0.0.0 --port 8000]   # Web 界面 + API + MCP
knowledge cli                                # 交互式控制台
knowledge serve                              # 仅 API + MCP
knowledge index <path>                       # 索引文件/目录
knowledge search "query" [--capability 4]    # 检索（可能力域过滤）
knowledge chat "问题" [--session ID]         # 问答（不带问题进交互式）
knowledge project "项目" [--stage 方案设计]   # 6 阶段项目引导
knowledge design "项目" [--llm-check]        # 生成方案文档
knowledge map [--capability 4] [--rebuild]   # 能力模型与知识覆盖
knowledge status                             # 系统状态
knowledge doctor                             # 健康检查
```

所有命令支持 `--json` 结构化输出。

---

## 🔌 外部 MCP 配置

编辑 `<KNOWLEDGE_HOME>/mcp.json`（格式参考 `knowledge/mcp.example.json`）：

```json
{
  "mcp": {
    "filesystem": {
      "type": "local",
      "command": ["npx", "-y", "@modelcontextprotocol/server-filesystem", "/path/to/data"],
      "enabled": true
    },
    "remote_service": {
      "type": "remote",
      "url": "https://example.com/mcp",
      "enabled": true,
      "headers": { "Authorization": "Bearer your-token" }
    }
  }
}
```

**支持两种类型：**
- `local`：stdio 启动（command + args）
- `remote`：Streamable HTTP（url + 可选 headers）

每个 server 在 agent 工具集中收敛为 **1 个工具**（如 `filesystem`），
调用时通过 `operation` 参数指定具体操作：

```
filesystem(operation="filesystem_list_directory", path="D:/")
filesystem(operation="filesystem_read_file", path="D:/x.txt")
```

> 工具参数 schema 自动从 MCP server 提取，LLM 能正确传参。

---

## 🏗️ 项目结构

```
├── src/
│   ├── agent/          # RAG Agent、工具、项目工作流、方案生成、外部 MCP 客户端
│   ├── api/            # FastAPI 服务、Web 界面、MCP Server 暴露
│   ├── capability/     # 工业视觉能力模型定义与知识映射
│   ├── cli/            # knowledge 命令（Typer）
│   ├── graph_store/    # 知识图谱（jieba/LLM 实体抽取）
│   ├── ingestion/      # 文档加载、切分、知识化（.hdev/代码解析）、向量化
│   ├── llm/            # LLM 客户端（DeepSeek / Ollama）
│   ├── retrieval/      # 混合检索、评分、查询重写
│   └── vector_store/   # Chroma 向量库
├── knowledge/
│   ├── templates/      # 工业视觉方案模板（缺陷/测量/OCR/定位）
│   └── mcp.example.json # 外部 MCP 配置模板
├── docs/               # 使用与部署文档
├── reports/            # 架构与性能报告
└── tests/              # 407 个测试
```

---

## 📊 数据目录

数据通过 `KNOWLEDGE_HOME` 环境变量定位（默认项目根）：

```
<KNOWLEDGE_HOME>/
├── .env                   # 配置
├── chroma_db/             # 向量库
├── data/
│   ├── docs/              # 源文档
│   ├── external/          # 外部导入资料
│   ├── chat_history/      # 会话历史
│   └── projects/          # 生成的方案文档
└── mcp.json               # 外部 MCP 配置
```

> `data/`、`chroma_db/`、`.env` 均已在 `.gitignore` 中排除，不会提交。

---

## 🧪 测试

```bash
python -m pytest tests/
# 407 passed
```

---

## 📚 文档

- [全局命令使用](docs/global-usage.md)
- [打包部署](docs/deployment.md)
- [CLI 设计](docs/cli-design.md)
- [知识库 CLI](docs/knowledge-cli.md)
- [架构与性能报告](reports/)

---

## 📄 License

MIT License
