# 个人知识库系统 · 详细架构文档

> 面向 **工业视觉 AI 工程师** 的智能知识库系统，以 AI 能力为核心组织知识，
> 通过 RAG（检索增强生成）+ 知识图谱 + Deep Agent 完成
> 「需求分析 → 知识研究 → 方案设计 → 算法实现 → 工程开发 → 项目验证」的全流程引导。

- 文档版本：1.2
- 适用代码：`main` 分支（426+ 个测试）
- 生成时间：2026-08-13

> 本次变更（v1.2）：将演进目标调整为 **标准单 Agent Web 客户端**，
> 明确 `web/` 独立前端源码、FastAPI 托管构建产物、轻量状态展示、
> Agent 权限模型、部署与数据目录策略。UI 细节见 `docs/ui-design.md`。

---

## 1. 项目概览

| 维度 | 说明 |
|------|------|
| 定位 | 面向工业视觉工程师的个人知识库（非通用问答系统） |
| 核心思想 | 知识按 **AI 能力域**（7 大域）组织，而非按工具/来源分类 |
| 检索方案 | 混合检索（向量 MMR + BM25 Ensemble）+ LLM 评分过滤 + 查询重写 + 上下文压缩 |
| 图谱增强 | NetworkX 有向图，jieba / LLM 双模式实体关系抽取 |
| Agent 框架 | Deep Agents（`create_deep_agent`），工具驱动 |
| 交互入口 | Web 客户端（主入口）/ FastAPI API / Typer CLI（启动与诊断）/ MCP Server（只读兼容入口）/ 飞书机器人 |
| 外部集成 | 支持配置式加载外部 MCP Server（opencode 风格 `mcp.json`） |
| Python 版本 | `>=3.10`（开发环境为 3.13） |

### 7 大能力域

| ID | 能力域 | 覆盖内容 |
|----|--------|----------|
| 1 | 需求分析 | 检测目标识别、技术指标提取、可行性评估 |
| 2 | 知识研究 | 知识检索、跨来源综合、技术选型调研 |
| 3 | 方案设计 | 成像系统、光学计算、算法方案、系统架构 |
| 4 | 算法实现 | 预处理/分割/定位/缺陷/测量/OCR/深度学习/3D |
| 5 | 工程开发 | 视觉程序、SDK 集成、PLC/机器人通讯、部署 |
| 6 | 项目验证 | 现场调试、鲁棒性、性能优化、验收 |
| 7 | 能力评估 | 方案评估、算法对比、持续优化 |

---

## 2. 技术栈与依赖

来自 `requirements.txt`（由 `pyproject.toml` 动态引入）：

| 类别 | 库 | 用途 |
|------|----|------|
| Agent | `deepagents>=0.5.0` | `create_deep_agent` 构建 RAG Agent |
| 核心框架 | `langchain>=0.3.0`、`langchain-classic>=1.0.0` | Chain/工具/`EnsembleRetriever` |
| 社区组件 | `langchain-community>=0.3.0` | 文档加载器、BM25Retriever |
| 向量存储 | `langchain-chroma>=1.0.0`、`chromadb>=0.5.0` | Chroma 持久化向量库 |
| Embedding | `langchain-huggingface`、`sentence-transformers` | bge 系列中文模型 |
| LLM | `langchain-openai` | DeepSeek / Ollama（OpenAI 兼容端点） |
| 切分 | `langchain-text-splitters` | `RecursiveCharacterTextSplitter` |
| 图谱 | `networkx`、`jieba` | 知识图谱与中文分词实体抽取 |
| BM25 | `rank-bm25` | 关键词检索 |
| PDF | `pymupdf` | PDF 加载 |
| CLI | `typer`、`click`、`rich`、`prompt_toolkit` | 双 CLI、进度条、交互式控制台 |
| Web | `fastapi`、`fastapi-mcp`、`uvicorn[standard]` | REST API + MCP Server + Web UI |
| 飞书 | `lark-oapi` | 飞书机器人长连接 |
| 配置 | `python-dotenv` | `.env` 加载 |

---

## 3. 总体架构

```
┌──────────────────────────────────────────────────────────────────────┐
│                            入口层 Entrypoints                         │
│   main.py · knowledge(entry.py) · kb.py · 飞书机器人(start_feishu.bat) │
└───────────────┬──────────────────────┬───────────────────────────────┘
                │                      │
        ┌───────▼────────┐    ┌────────▼─────────┐
        │  CLI 层         │    │  API 层           │
        │  cli/           │    │  api/             │
        │  Typer+Click+   │    │  FastAPI + Web    │
        │  交互式控制台     │    │  + MCP Server    │
        └───────┬────────┘    └────────┬─────────┘
                │                      │
                └──────────┬───────────┘
                           ▼
                ┌───────────────────────┐
                │  Agent 层  agent/      │  ← Deep Agent（工具编排）
                │  工具: retrieve_knowledge │
                │       retrieve_graph     │
                │       project_workflow   │
                │       (外部 MCP 工具)      │
                └───────────┬───────────┘
                            │
        ┌───────────────────┼───────────────────────┐
        ▼                   ▼                       ▼
┌──────────────┐   ┌──────────────────┐   ┌──────────────────┐
│ 检索 retrieval │   │ 图谱 graph_store   │   │ 能力模型 capability │
│ 混合检索        │   │ NetworkX 有向图    │   │ 7 域规则映射        │
│ 评分/重写/压缩   │   │ jieba/LLM 抽取    │   │ 知识→能力标签        │
└──────┬───────┘   └────────┬─────────┘   └────────┬─────────┘
       │                    │                      │
       ▼                    ▼                      │
┌──────────────┐   ┌──────────────────┐            │
│ vector_store  │   │   ingestion 摄取    │◄─────────┘
│ Chroma + BM25 │   │ 加载/切分/知识化/向量化│
│ embedding 模型 │   │ 文件追踪增量更新     │
└──────────────┘   └────────┬─────────┘
                            │
                     ┌──────▼──────┐
                     │  llm 客户端  │
                     │ DeepSeek/   │
                     │ Ollama      │
                     └─────────────┘
```

**核心中介**：`src/resources.py` 的 `ResourceManager` 单例负责全局生命周期——
加载 Embedding 模型、LLM、Chroma、知识图谱、BM25 索引，并缓存 RAG Agent，
是 API 与 CLI 共享的资源持有者。

---

## 3.1 目标架构：标准单 Agent Web 客户端

后续演进目标不是通用后台系统，也不是多租户 SaaS，而是 **本地单用户 Knowledge Agent Web 客户端**。
用户主要通过浏览器 Web 客户端使用同一个 Knowledge Agent；API 是 Web 的一等后端接口；
CLI 保留启动、诊断和工程化索引入口；MCP 作为外部 Agent 的只读兼容入口。

### 目标运行形态

```
浏览器 Web 客户端（主入口）
  │  HTTP / POST streaming SSE
  ▼
FastAPI API（托管 web/dist + /api/v1/*）
  │
  ▼
Application Use Cases（chat/search/index/status/session）
  │
  ├── Single Agent Runtime（Deep Agent，负责对话编排）
  │       └── Agent tools 只调用应用用例，不直接操作 Chroma/BM25/Graph
  │
  ├── Knowledge Services（检索、摄取、图谱、能力域映射）
  │
  ├── Observability（状态展示、深度诊断、可选修复建议）
  │
  └── Infrastructure（Chroma、BM25、Embedding、LLM、NetworkX、文件系统、MCP Client）
```

### 目标代码布局

代码目录和模块名使用英文；架构文档、领域解释、提示词和 UI 文案可以使用中文。
目标结构采用模块化单体，不拆微服务：

```
langchain-kb/
├── web/                         # Vite + React + TypeScript 前端源码
│   ├── src/
│   │   ├── app/                 # App shell、路由、全局布局
│   │   ├── pages/               # Chat / Knowledge / Status / Settings
│   │   ├── components/          # 共享 UI 与特性组件
│   │   ├── api/                 # typed API client + streaming client
│   │   ├── hooks/               # useChat/useStatus/useSessions 等
│   │   ├── styles/              # tokens、全局样式
│   │   └── types/               # API 响应类型
│   └── dist/                    # 构建产物，由 FastAPI 托管
│
└── src/kb/                      # 目标 Python 包（迁移完成后的主包）
    ├── bootstrap/               # 启动、依赖组装、生命周期、依赖检查
    ├── config/                  # 配置加载、路径解析、环境变量校验
    ├── interfaces/              # 入站适配器
    │   ├── api/                 # FastAPI REST + streaming endpoints
    │   ├── cli/                 # knowledge web/status/doctor/index
    │   ├── mcp/                 # 只读兼容工具
    │   └── feishu/              # 飞书消息适配
    ├── agent/                   # 单 Agent 运行时
    │   ├── runner.py            # invoke/stream 统一入口
    │   ├── factory.py           # create_deep_agent 组装
    │   ├── tools.py             # 工具注册，薄适配到 application
    │   ├── prompts.py           # 系统提示词
    │   └── events.py            # 流式事件模型
    ├── application/             # 系统用例
    │   ├── chat.py              # ChatWithAgent
    │   ├── search.py            # SearchKnowledge
    │   ├── indexing.py          # IndexDocuments / RemoveDocument
    │   ├── documents.py         # KnowledgeStats / ListDocuments（后续）
    │   ├── graph.py             # SearchGraph / RebuildGraph
    │   ├── sessions.py          # 会话管理
    │   └── status.py            # GetSystemStatus / RunDiagnostics
    ├── knowledge/               # 知识库业务能力
    │   ├── retrieval.py         # 混合检索、重写、评分、压缩
    │   ├── ingestion.py         # 加载、知识化、切分、去重
    │   ├── graph.py             # 图谱业务操作
    │   ├── capability.py        # 7 大能力域映射
    │   └── ranking.py           # 排序/裁剪策略
    ├── domain/                  # 稳定领域对象
    │   ├── messages.py
    │   ├── documents.py
    │   ├── search.py
    │   ├── graph.py
    │   ├── indexing.py
    │   └── status.py
    ├── infrastructure/          # 技术适配器
    │   ├── chroma/
    │   ├── bm25/
    │   ├── embeddings/
    │   ├── llm/
    │   ├── graph_store/
    │   ├── filesystem/
    │   ├── session_store/
    │   └── external_mcp/
    └── observability/           # 状态、健康检查、自检、诊断报告
        ├── status_registry.py
        ├── monitor.py
        ├── health.py
        └── diagnostics.py
```

### 依赖规则

- `interfaces/*` 只做协议适配、参数校验、结果呈现，不直接操作 Chroma、BM25、NetworkX、LLM。
- Web 前端只调用 `/api/*`，不得依赖后端内部文件结构或运行时路径。
- `agent/tools.py` 只调用 `application/*` 用例，不直接调用 `retrieval/*`、`vector_store/*`、`graph_store/*`。
- `application/*` 是用例边界，统一承载 Chat、Search、Index、Status、Session 等系统能力。
- `knowledge/*` 承载知识库业务规则，隐藏检索、摄取、图谱拼装细节。
- `infrastructure/*` 承载具体 SDK 与存储实现，可依赖第三方库，但不得 import `interfaces/*`。
- `observability/*` 提供运行状态和诊断能力；状态展示默认轻量，深度诊断必须显式触发。

### Agent 权限模型

Single Agent 是主交互能力，但不是无限权限执行器：

| 能力 | Agent 第一阶段权限 | 执行入口 |
|------|-------------------|----------|
| 检索知识、回答问题 | 可直接执行 | `SearchKnowledge` / `ChatWithAgent` |
| 查看轻量系统状态 | 可直接执行 | `GetSystemStatus` |
| 添加资料、删除资料 | 只能建议，不能直接执行 | Web Knowledge 页面或 CLI 显式确认 |
| 重建索引、修复系统 | 只能建议，不能直接执行 | Status/Knowledge 异常详情或 CLI 显式确认 |
| 修改配置、写入密钥 | 禁止执行 | 用户手动编辑配置文件 |

当用户要求 Agent 改变知识库状态时，Agent 只解释影响并引导打开对应 UI 流程，
最终动作必须由用户在 Web/CLI 中显式确认。

### API、CLI、MCP 定位

| 入口 | 第一阶段定位 | 说明 |
|------|--------------|------|
| Web | 主产品入口 | `web/` 独立源码，构建后由 FastAPI 托管 |
| API | 一等入口 | Web 和外部客户端都通过标准 `/api/v1/*` 调用 |
| CLI | 启动与诊断入口 | 正式保留 `knowledge web/status/doctor/index`，Chat/Search 优先走 Web |
| MCP | 只读兼容入口 | 暴露 `consult_knowledge`、`search_knowledge`、`get_system_status`，不暴露写操作 |
| 飞书 | 兼容入口 | 通过 API 调用聊天能力，不直接访问底层模块 |

Chat 流式输出采用 **POST + fetch readable stream**，事件使用 SSE 文本格式，第一版事件类型：
`message_start / token / sources / message_end / error`。前端必须支持停止生成；中断后的半截回答保存到会话历史并标记 `interrupted=true`。

### 部署与数据目录策略

第一阶段以本机源码运行为主，兼容局域网访问；后续可演进为安装包/可执行包。

- 开发态：FastAPI 后端运行在 `127.0.0.1:8000`，Vite dev server 代理 `/api/*`。
- 使用态：前端 `web/dist` 由 FastAPI 托管，用户只需运行 `knowledge web`。
- 默认监听 `127.0.0.1` 时不要求登录。
- 局域网模式（例如 `0.0.0.0`）必须配置简单访问 token，不引入完整账号系统。
- 用户数据默认放平台应用数据目录，`KNOWLEDGE_HOME` 可覆盖：
  - Windows：`%LOCALAPPDATA%/KnowledgeAgent`
  - Linux：`~/.local/share/knowledge-agent`
  - macOS：`~/Library/Application Support/KnowledgeAgent`
- 安装目录或源码目录只放程序文件、前端构建产物和配置模板，不默认写入用户数据。

### 启动与状态展示策略

启动采用混合模式：致命依赖阻止启动，可降级问题进入 Web 状态页展示。

| 类型 | 示例 | 行为 |
|------|------|------|
| 致命依赖 | Python 版本不支持、数据目录不可写、配置无法解析、端口占用、局域网模式无 token | 阻止启动并输出可操作错误 |
| 可降级问题 | LLM key 缺失、BM25 缓存缺失、Graph 缺失、MCP 未配置、模型未缓存 | 允许启动，Status 页面展示影响和修复建议 |

状态展示分为三层：

- 顶部 System Rail：轻量展示 `embedding → llm → vector → bm25 → graph → agent`。
- Status 页面：整体状态、关键指标、问题列表、一个“运行完整诊断”主操作。
- 深度诊断：显式触发，默认只读；自动修复必须由用户确认，且不授予 Agent 默认修复权限。

### 现状差距与迁移路线

当前代码仍按 `src/api`、`src/agent`、`src/retrieval`、`src/ingestion` 等领域目录组织。
目标架构应分阶段迁移，避免一次性移动文件造成行为回归。

1. **文档阶段**：固化本目标架构与 `docs/ui-design.md`，不改变运行行为。
2. **前端阶段**：新增 `web/` 工程和 FastAPI 静态托管，保留旧 `src/api/web.py` 直到新 UI 可用。
3. **Chat 阶段**：新增 `ChatWithAgent` 用例和 `POST /api/v1/chat/stream`，Web/CLI/API 共享同一聊天链路。当前已进一步落地 `src/application/chat_orchestrator.py` 与 `src/bootstrap/composition.py`：应用层只依赖 `ChatPort`，旧 API 服务通过兼容适配器接入，CLI 已切换到应用层入口；同步问答、流式工具事件、审批中断与恢复均通过 `AgentRuntime` 执行。Agent 工具由 `HarnessRuntime.tools` 统一注册，RAG Agent 首次构建时从该注册表装配本地工具和 MCP 工具。
4. **Search 阶段**：抽出 `SearchKnowledge` 用例，让 Agent 工具、API 搜索、Web 搜索共用一条检索链路。
5. **Status 阶段**：把现有 `src/status.py`、`src/monitor.py` 收敛到 `observability` 语义下，保持 `selfcheck.py` 独立入口。
6. **Index 阶段**：把 `ingestion/pipeline.py` 的横切流程收敛到 `IndexDocuments` 用例。
7. **包结构阶段**：在用例边界稳定后再迁移到 `src/kb/`，清理旧模块和兼容路径。

---

## 4. 功能模块总览

系统按「能力」划分为 11 个功能模块。每一模块列出：**功能定位 → 主要能力 → 触发入口 → 支撑代码**。

### 4.1 知识摄取与索引（Ingestion）

| 项 | 说明 |
|----|------|
| 功能定位 | 把原始资料转成可检索的知识 |
| 主要能力 | 多格式加载（md/txt/pdf/代码/`.hdev`）；`.hdev`/代码→Markdown 知识化；递归切分；向量化写入；BM25 重建；知识图谱构建；内容哈希增量追踪与去重 |
| 触发入口 | `knowledge index <path>`、控制台 `/add /ingest /rebuild`、API `POST /documents/index`、`main.py ingest/add/update` |
| 支撑模块 | `ingestion`、`vector_store`、`retrieval`、`graph_store` |
| 关键文件 | `src/ingestion/pipeline.py`、`loader.py`、`knowledge_extract.py`、`tracker.py` |

### 4.2 混合检索与检索增强（RAG 内核）

| 项 | 说明 |
|----|------|
| 功能定位 | 从向量库与关键词索引中召回最相关内容，并做质量增强 |
| 主要能力 | Chroma MMR + BM25 加权融合；能力域过滤（`capability_domain_primary $eq`）；LLM 并行相关性评分；全不相关自动查询重写；LLM 并行上下文压缩；知识图谱关联拼装 |
| 触发入口 | Agent 工具 `retrieve_knowledge`、API `POST /retrieval/search`、CLI `knowledge search` |
| 支撑模块 | `retrieval`、`vector_store`、`graph_store`、`llm` |
| 关键文件 | `src/agent/tools.py`、`src/retrieval/retriever.py`、`grading.py`、`rewrite.py` |

### 4.3 知识图谱（Knowledge Graph）

| 项 | 说明 |
|----|------|
| 功能定位 | 实体/关系层面的知识关联增强 |
| 主要能力 | jieba 词性抽取 / LLM 批量抽取（失败降级 jieba）；全量与增量合并（关系去重）；匹配实体 2 层 BFS 子图搜索；JSON 原子持久化；`/mode` 双模式切换 |
| 触发入口 | 自动随索引构建；Agent 工具 `retrieve_graph`；CLI `graph_search`、`build_graph` |
| 支撑模块 | `graph_store` |
| 关键文件 | `src/graph_store/graph.py`、`extraction.py`、`extraction_llm.py`、`service.py` |

### 4.4 智能问答 Agent（RAG 对话）

| 项 | 说明 |
|----|------|
| 功能定位 | 基于 Deep Agent 的检索增强问答与项目引导 |
| 主要能力 | `create_deep_agent` 工具编排；流式回答；多轮会话；会话 JSON 持久化/恢复/删除/列表；超长历史 LLM 压缩；引用来源标注 `[来源: 文件名]` |
| 触发入口 | `knowledge chat`、`knowledge cli`、Web 聊天、API `POST /chat`、MCP、飞书 |
| 支撑模块 | `agent`、`llm`、`retrieval`、`vector_store`、`graph_store` |
| 关键文件 | `src/agent/rag_agent.py`、`tools.py`、`chat_history.py` |

### 4.5 工业视觉方案生成（Design 流水线）

| 项 | 说明 |
|----|------|
| 功能定位 | 一句话需求 → 结构化初版方案文档 |
| 主要能力 | LLM 需求解析为结构化字段；规则表+cap4 检索+LLM 算子细化的算法推荐；按能力域检索知识并生成 10 节方案；落盘 5 个 Markdown；可选 LLM 质量/风险/完整性检查；脱敏 LLM 调用审计日志 |
| 触发入口 | `knowledge design "PCB缺陷检测"`、`knowledge project` |
| 支撑模块 | `agent`、`capability`、`knowledge/templates` |
| 关键文件 | `src/agent/requirement_analyzer.py`、`algorithm_selector.py`、`solution_generator.py`、`project_report.py`、`project_workflow.py` |

### 4.6 能力模型与知识地图（Capability）

| 项 | 说明 |
|----|------|
| 功能定位 | 知识→AI 能力域的规则映射与覆盖统计 |
| 主要能力 | 7 域/11 技术/9 场景分类词典；文件名+内容双层规则映射（零 LLM）；向量写入时自动注入能力标签；`map --rebuild` 历史补标；按域覆盖统计 |
| 触发入口 | `knowledge map [--capability N] [--rebuild]`；索引时自动生效 |
| 支撑模块 | `capability` |
| 关键文件 | `src/capability/model.py`、`mapper.py` |

### 4.7 外部 MCP 集成（MCP Client）

| 项 | 说明 |
|----|------|
| 功能定位 | 让 Agent 调用外部 MCP Server 工具 |
| 主要能力 | 解析 opencode 风格 `mcp.json`（local stdio / remote streamable-http）；默认将每个 MCP operation 暴露为独立工具；可通过 `MCP_TOOL_MODE=dispatch` 使用每 server 一个分发工具；危险工具审批与 checkpoint resume；异步工具同步化桥接；失败优雅降级 |
| 触发入口 | 配置 `<KNOWLEDGE_HOME>/mcp.json` 后自动随 Agent 加载 |
| 支撑模块 | `agent` |
| 关键文件 | `src/agent/mcp_client.py` |

### 4.8 Web/API 服务与 MCP Server

| 项 | 说明 |
|----|------|
| 功能定位 | 对外提供 REST、Web UI 与 MCP Server 三合一服务 |
| 主要能力 | 9 个 `/api/v1` 路由（健康/状态监控/搜索/问答/索引/会话）；内嵌单文件 Web UI（暗色模式+会话侧栏+来源展示+组件状态条）；`FastApiMCP` 暴露 3 个工具；统一错误协议与异常处理；异步索引任务管理 |
| 触发入口 | `knowledge web`、`knowledge serve`、`main.py api` |
| 支撑模块 | `api`、`resources` |
| 关键文件 | `src/api/app.py`、`routers/`、`services/`、`schemas.py` |

### 4.9 CLI 与交互式控制台

| 项 | 说明 |
|----|------|
| 功能定位 | 命令行全功能入口与交互式会话 |
| 主要能力 | Typer 主 CLI（web/cli/serve/index/search/chat/project/design/map/status/doctor/lark）；全部命令 `--json` 输出与语义化错误码；Rich 进度条；交互式控制台（后台线程预加载 Agent + 15 个 `/` 命令，含 `/status` 组件状态监控）；首次运行 API Key 引导；遗留 Click CLI 兼容；项目自检为独立程序 `selfcheck.py` |
| 触发入口 | `knowledge ...`、`python main.py` |
| 支撑模块 | `cli` |
| 关键文件 | `src/cli/knowledge.py`、`console.py`、`commands.py`、`kb.py`、`api_key.py` |

### 4.10 飞书机器人（Feishu/Lark）

| 项 | 说明 |
|----|------|
| 功能定位 | 在飞书中使用知识库问答 |
| 主要能力 | `lark-oapi` 长连接（WebSocket）免公网 URL；文本转发 `POST /api/v1/chat`；每用户独立会话（`/new` 重置）；open_id→session_id 映射持久化 |
| 触发入口 | `knowledge lark`、`start_feishu.bat` |
| 支撑模块 | `feishu` |
| 关键文件 | `src/feishu/bot.py`、`session_map.py` |

### 4.11 支撑基础设施

| 项 | 说明 |
|----|------|
| 功能定位 | 全局配置、资源生命周期、LLM 客户端 |
| 主要能力 | `.env` 加载与路径解析；`ResourceManager` 5 步启动/关闭/缓存失效；DeepSeek 与 Ollama 双 LLM 客户端（lru_cache） |
| 触发入口 | 所有入口隐式依赖 |
| 支撑模块 | `config.py`、`resources`、`llm` |
| 关键文件 | `src/resources.py`、`src/llm/client.py` |

### 功能模块 ↔ 代码目录映射

```
功能模块                    代码目录
─────────────────────────   ─────────────────────────────
4.1 知识摄取与索引            src/ingestion/ + vector_store/
4.2 混合检索与检索增强         src/retrieval/ + vector_store/
4.3 知识图谱                  src/graph_store/
4.4 智能问答 Agent            src/agent/ + src/llm/
4.5 工业视觉方案生成           src/agent/ + capability/
4.6 能力模型与知识地图          src/capability/
4.7 外部 MCP 集成             src/agent/mcp_client.py
4.8 Web/API 与 MCP Server    src/api/
4.9 CLI 与交互式控制台         src/cli/
4.10 飞书机器人               src/feishu/
4.11 支撑基础设施             config.py + src/resources.py + src/llm/
```

### 功能调用关系

```
4.11 支撑基础设施（config / resources / llm）
   │ 被以下所有功能依赖
   ▼
4.1 摄取 → 写入 4.6 能力标签、4.2 索引(BM25)、4.3 图谱
   │
4.2 检索增强 ──► 供 4.4 问答 / 4.5 方案生成 检索
4.3 知识图谱 ──► 供 4.4 问答 增强关联
4.6 能力模型 ──► 供 4.1 打标签、4.5 分章节检索、4.9 map 统计
   │
4.4 智能问答 ──► 通过 4.9 CLI/4.8 Web/4.10 飞书 暴露
4.5 方案生成 ──► 通过 4.9 CLI 暴露
4.7 外部 MCP ──► 注入 4.4 Agent 工具集
4.8 Web/API ──► 调用 4.2/4.4/4.1 的能力；对外兼作 MCP Server
```

---

## 5. 目录结构详解

```
langchain-kb/
├── config.py                  # 全局配置（唯一配置入口，加载 .env）
├── main.py                    # 遗留调度入口（api/kb/knowledge/console）
├── selfcheck.py               # ★ 项目自检独立程序（10 项探测 + 自动修复）
├── pyproject.toml             # 打包定义，入口点 knowledge=src.cli.entry:main
├── requirements.txt           # 运行时依赖（pyproject 动态引入）
├── .env.example               # 安全配置模板
├── src/
│   ├── resources.py           # ★ ResourceManager 单例 + app_lifespan（5 步启动）
│   ├── status.py              # ★ 监控层：组件状态注册表 + 整体状态推导（L4）
│   ├── capability/            # 能力模型与知识→能力映射
│   │   ├── model.py           #   7 能力域/技术/场景分类词典
│   │   └── mapper.py          #   文件名+内容双层规则映射 classify_chunk()
│   ├── llm/                   # LLM 客户端（缓存）
│   │   └── client.py          #   get_llm (DeepSeek) / get_local_llm (Ollama)
│   ├── ingestion/             # 文档摄取管道
│   │   ├── loader.py          #   MarkdownLoader/load_path，支持 md/txt/pdf/代码/hdev
│   │   ├── knowledge_extract.py  # .hdev XML→Markdown、代码→知识概览
│   │   ├── splitter.py        #   RecursiveCharacterTextSplitter
│   │   ├── pipeline.py        #   run_ingestion/run_add_path/增量/单文件/删除
│   │   └── tracker.py         #   file_tracker.json 内容哈希增量追踪
│   ├── vector_store/          # 向量存储
│   │   ├── embedding.py       #   bge 系列 / openai，GPU 自动探测
│   │   ├── chroma_client.py   #   Chroma 单例、能力标签注入、批量写入
│   │   └── service.py         #   VectorStoreService（检索器工厂/统计/重建）
│   ├── retrieval/             # 检索增强
│   │   ├── retriever.py       #   BM25 索引构建/磁盘缓存/混合检索
│   │   ├── grading.py         #   LLM 文档相关性评分
│   │   └── rewrite.py         #   LLM 查询重写
│   ├── graph_store/           # 知识图谱
│   │   ├── graph.py           #   KnowledgeGraph（networkx + JSON 持久化）
│   │   ├── extraction.py      #   jieba 实体/关系抽取
│   │   ├── extraction_llm.py  #   LLM 批量抽取（失败降级 jieba）
│   │   ├── retriever.py       #   get_graph/set_graph 全局单例
│   │   └── service.py         #   GraphService 门面
│   ├── agent/                 # Agent 层
│   │   ├── rag_agent.py       #   create_rag_agent + stream_rag_response
│   │   ├── tools.py           #   retrieve_knowledge / retrieve_graph 工具
│   │   ├── project_workflow.py#   project_workflow 工具（6 阶段引导）
│   │   ├── requirement_analyzer.py # 需求→结构化字段（1 次 LLM）
│   │   ├── algorithm_selector.py   # 规则表+cap4 检索+LLM 算子细化
│   │   ├── solution_generator.py   # 按能力域检索+1 次 LLM 生成 10 节方案
│   │   ├── project_report.py  #   Markdown 落盘 + llm_log.jsonl
│   │   ├── chat_history.py    #   会话 JSON 持久化/压缩/列表
│   │   └── mcp_client.py      #   外部 MCP 工具加载（每 server 收敛 1 工具）
│   ├── api/                   # Web 服务
│   │   ├── app.py             #   create_app() + FastApiMCP 挂载
│   │   ├── dependencies.py    #   RmDep 依赖注入（未就绪返回 503）
│   │   ├── schemas.py         #   Pydantic 请求/响应模型
│   │   ├── web.py             #   内嵌单文件 Web UI（HTML+CSS+JS）
│   │   ├── routers/           #   health/status/search/chat/indexing/sessions
│   │   └── services/          #   服务层（chat/search/indexing/health/status）
│   ├── cli/                   # 命令行
│   │   ├── entry.py           #   UTF-8 stdout 包装 + 入口
│   │   ├── knowledge.py       #   ★ 主 CLI（Typer，11 命令 + status/doctor/map）
│   │   ├── console.py         #   交互式控制台（后台线程加载 Agent）
│   │   ├── commands.py        #   遗留 Click CLI（14 命令）
│   │   ├── kb.py              #   遗留 kb 子命令组
│   │   └── api_key.py         #   首次运行 DeepSeek Key 引导
│   └── feishu/                # 飞书机器人
│       ├── bot.py             #   长连接模式，转发 /api/v1/chat
│       └── session_map.py     #   open_id→session_id 映射持久化
├── knowledge/
│   ├── templates/             # 工业视觉方案模板（缺陷/测量/OCR/定位）
│   └── mcp.example.json       # 外部 MCP 配置模板
├── docs/                      # 使用与部署文档
├── reports/                   # 架构/性能/MCP 验收报告
├── evals/                     # 评估脚本与评测语料
├── tests/                     # 480 个 pytest 测试（含监控层与监控修复程序）
└── chroma_db/                 # 运行时数据（git 忽略）
```

---

## 6. 核心模块详解

### 6.1 配置层 `config.py`

- **路径解析原则**：所有相对路径锚定 `KNOWLEDGE_HOME`（优先级：环境变量 > wheel 安装时的平台应用数据目录 > 项目根）。
- 加载 `<KNOWLEDGE_HOME>/.env`；关键配置：`DEEPSEEK_API_KEY`、`EMBEDDING_MODEL`、
  `CHUNK_SIZE`、`TOP_K`、`RERANK_LLM`（deepseek/local）、`MCP_CONFIG_PATH`、
  `ENABLE_GRADING/REWRITE/HYBRID_SEARCH/CONTEXT_COMPRESSION/GRAPH/GRAPH_LLM_EXTRACTION` 等开关。
- 设置 `HF_ENDPOINT` 与 `HF_HUB_DISABLE_SYMLINKS_WARNING` 环境变量。
- `ensure_data_dirs()` 幂等创建数据目录骨架。

### 6.2 资源生命周期 `src/resources.py`

`ResourceManager`（单例，线程安全懒加载）承担全局初始化，5 步启动流程：

```
[1/5] Embedding 模型加载 → [2/5] LLM 客户端 → [3/5] Chroma 连接
    → [4/5] 知识图谱加载 → [5/5] BM25 索引构建
```

- 持有并缓存 `agent`（无状态，可跨请求复用）、`_ensemble_retriever`（按 k 缓存）。
- `invalidate_retriever_cache()` 在数据变更后使缓存失效并递增索引版本号。
- `app_lifespan` 供 FastAPI lifespan 使用，保证 API 启动即完成全部资源初始化。
- 每次 `startup()`/`get_agent()` 向监控层上报组件状态（见 6.2.1）。

### 6.2.1 监控层 `src/status.py`（L4）

进程级组件状态注册表，不依赖任何业务模块。状态机：

```
pending（未启动）→ loading（初始化中）→ ready（就绪）
                 └──────────────→ error（失败）
disabled（功能关闭，不参与就绪判定）
```

- **受监控组件**：`embedding / llm / vector_store / bm25 / graph / agent / index`。
- **上报接入点**：
  - `ResourceManager.startup()`：5 步启动逐组件 `loading → ready`；
    启动失败时把仍处于 `loading` 的组件标记为 `error` 并回滚。
  - `ResourceManager.get_agent()` / `create_rag_agent()`：Agent 惰性构建状态；
    失败由 `get_agent()` 与控制台后台加载线程标记 `error`。
  - `retriever.rebuild_bm25()`：磁盘加载/全量重建/已在内存三态，detail 带 chunk 数。
  - `api/services/indexing.run_index_task()`：异步索引任务 `loading → ready/error`。
  - `ResourceManager.shutdown()`：复位为 `pending`。
- **整体状态推导** `overall_state()`：核心组件（embedding/llm/vector_store）
  任一失败 → `error`；核心就绪且可选组件（bm25/graph）失败 → `degraded`；
  核心就绪 → `ok`；其余 → `pending`。
- **消费端**：`GET /api/v1/status`（含各组件 state/detail/duration_ms/error +
  整体状态 + 数据规模）、控制台 `/status`（Agent 加载完成前即可用）、
  Web 落地页顶部状态条（10s 轮询刷新）。

### 6.2.2 项目自检程序 `selfcheck.py`（L4 独立工具）

**独立程序**（不依赖 CLI/API），一键诊断项目各关键组件并可选自动修复：

```
python selfcheck.py                 # 只读自检
python selfcheck.py --repair         # 自检 + 自动修复失败且可修复的组件
python selfcheck.py --check bm25,graph   # 只自检指定组件
python selfcheck.py --json           # JSON 输出
```

自检引擎在 `src/monitor.py`（`python -m src.monitor` 亦可直接运行）。

- **10 项检查**：registry（注册表卡死检测，>300s 的 loading 判为卡死）、
  data_dirs、embedding、llm（含 `DEEPSEEK_API_KEY` 检测）、vector_store
  （含 Windows 非 ASCII 路径告警）、bm25（内存/磁盘缓存/计数失效三级判定）、
  graph（文件缺失/损坏/实体数为 0 判定）、agent（惰性构建正常、error 需修复）、
  index（索引任务卡死检测，>600s 的 running 判为卡死）、tmp_files
  （`*.pkl.tmp`/`*.tmp` 遗留清理）。
- **可自动修复项**：registry 卡死解挂、data_dirs 创建、bm25 全量重建、
  graph 从文档重建、agent 重新构建、index 卡死任务终止、tmp_files 删除。
  不可自动修复项（llm 缺 key、向量库路径问题）给出明确修复建议。
- 探测结果同步回写监控层注册表，使 `/api/v1/status` 反映真实探测状态。
- 退出码：0 全部通过 / 1 存在未修复失败 / 2 自动修复后仍失败。

### 6.3 能力模型与映射 `src/capability/`

- `model.py`：7 能力域（含中文/英文关键词）、11 种技术（从文件名猜）、9 种工业场景。
- `mapper.py`：`classify_chunk(source, text)` 双层规则映射——
  文件名规则表（`.hdev→算法实现`、`solution_guide_iii_a→1D 测量` 等）+ 内容关键词，
  输出多标签元数据：`capability_domain`（多标签逗号串）、`capability_domain_primary`（用于 Chroma `$eq` 过滤）、
  `capability_items`、`scene`、`technology`、`confidence`、`mapping_method`。
- 完全规则化（无 LLM），在向量化写入时自动注入（`_inject_capability_metadata`），
  也支持 `knowledge map --rebuild` 对历史 chunks 补打标签。

### 6.4 摄取管道 `src/ingestion/`

**加载**（`loader.py`）：支持 `.md/.txt/.pdf`、源代码（`.c/.cpp/.cs/.vb/.py/.h/.hpp`）、`.hdev`；
`source` 元数据为相对路径。

**知识化**（`knowledge_extract.py`）：
- `.hdev`：解析 HALCON XML，提取 `<procedure>` 的过程名、注释（`<c>`）、算子调用链（`<l>`），渲染为结构化 Markdown。
- 源代码：启发式提取头部注释、`class/def/函数签名` 符号、API 调用，生成「代码文件知识概览」。

**切分**（`splitter.py`）：`RecursiveCharacterTextSplitter(chunk_size=500, overlap=80)`，
分隔符优先按 Markdown 标题、代码块、段落、中文句号。

**四条索引路径**（`pipeline.py`）：

| 函数 | 触发 | 行为 |
|------|------|------|
| `run_ingestion` | `/ingest`、`ingest`、`index` | 全量加载 DATA_DIR → 切分 → 向量化 → 重建 BM25 → 重建图谱 → 更新追踪 |
| `run_add_path` | `/add`、`add`、`index <path>` | 复制到 `data/external/`（重名自动加后缀、图片忽略）→ 向量化 → 图谱增量 |
| `run_incremental_update` | `update`、`index --incremental` | 哈希比对 → 删除旧 chunks → 只索引变更文件 |
| `run_single_file_update` | `update_file`、`index <file>` | 单文件删除+重建 |

**去重追踪**（`tracker.py`）：`file_tracker.json` 记录 `internal/external` 两类文件的
`mtime+size` 的 MD5 哈希；`is_already_indexed()` 防止重复摄取。

### 6.5 向量存储 `src/vector_store/`

- `embedding.py`：`get_embedding_model()`（lru_cache）——默认 `BAAI/bge-small-zh-v1.5`，
  自动探测 CUDA；`EMBEDDING_MODEL=openai` 时切 `OpenAIEmbeddings`。
- `chroma_client.py`：Chroma 单例（`collection="langchain_docs"`），`_inject_capability_metadata`
  在写入前为 chunks 附加能力标签；`add_documents_with_progress` 分批量写入并输出 ASCII 进度条。
- `service.py`：`VectorStoreService` 门面，提供：
  - `get_retriever(k, capability)`：能力域过滤时在 MMR 检索中加入 `capability_domain_primary: $eq` 过滤；
    混合模式用 `EnsembleRetriever([vector, bm25], weights=[0.5, 0.5])`。
  - `reset()`（删除集合）、`get_stats()`（chunk 数 + 来源列表）、`rebuild_bm25()`。

### 6.6 检索增强 `src/retrieval/`

- `retriever.py`：BM25 索引的构建与**磁盘缓存**（`chroma_db/bm25_index.pkl`，
  按 collection count 校验有效性避免数据变更后误用）；模块级 `_bm25_retriever` 全局单例。
- `grading.py`：`grade_document` 让 LLM 判断「相关/不相关」。
- `rewrite.py`：`rewrite_question` 查询意图改写。

### 6.7 知识图谱 `src/graph_store/`

- `graph.py`：`KnowledgeGraph`（NetworkX `DiGraph`），JSON 原子持久化（临时文件+replace）；
  `build_from_chunks`（全量）/`add_chunks`（增量，边关系合并去重）。
  `search(query)` 以匹配实体为种子做 **2 层 BFS 子图扩展**（上限 30 节点）并输出实体/关系/来源。
- `extraction.py`（jieba 模式）：`jieba.posseg` 词性映射实体类型
  （nr→Person, ns→Location, nz→Technology, eng→Tool, n→Concept），
  同句共现实体生成 `co_occur` 关系。
- `extraction_llm.py`（LLM 模式）：批量 prompt 抽取实体/关系（类型白名单校验），
  **任一批失败自动降级 jieba**，避免整库构建失败。
- 模式由 `ENABLE_GRAPH_LLM_EXTRACTION` 控制（`/mode llm|jieba` 切换并持久化到 `.env`）。

### 6.8 Agent 层 `src/agent/`

**Agent 构建**（`rag_agent.py`）：`create_rag_agent()` 依次初始化
embedding 模型 → 向量库 → BM25 → LLM，然后 `create_deep_agent(model, tools, system_prompt)`。
工具集：

| 工具 | 说明 |
|------|------|
| `retrieve_knowledge` | 主检索工具：混合检索 → LLM 评分过滤（全不相关自动重写）→ 上下文压缩 → 图谱关联拼接 |
| `retrieve_graph` | 纯图谱检索 |
| `project_workflow` | 按 6 阶段引导项目（能力域过滤检索） |
| 外部 MCP 工具 | 默认每个 MCP operation 一个独立工具（带 server 前缀）；兼容模式下每个 server 一个 `operation` 分发工具 |

**检索编排**（`tools.py`）：`retrieve_knowledge` 内部使用 `ThreadPoolExecutor` 并发评分/压缩
（上限 5 workers）；评分/压缩使用的 LLM 由 `RERANK_LLM` 决定云端 DeepSeek 或本地 Ollama。

**外部 MCP**（`mcp_client.py`）：解析 opencode 风格 `mcp.json`（local stdio / remote streamable-http），
用 `MultiServerMCPClient` 连接，`_server_dispatch_tool` 把 server 的所有操作合并成单一
`StructuredTool`（动态构建 Pydantic schema，参数自动提取）；失败优雅降级不影响本地工具。

**方案生成（Stage 4）**：`requirement_analyzer` → `algorithm_selector`（规则表+cap4 检索+LLM 细化）→
`solution_generator`（按 10 章节分别从对应能力域检索知识 + 1 次 LLM 组装）→
`project_report` 落盘 5 个 Markdown 文件 + `llm_log.jsonl`（脱敏的调用审计日志）。

**会话历史**（`chat_history.py`）：`data/chat_history/*.json`，`compress_history` 用 LLM
把超长历史压缩为摘要（保留最近 10 轮）；标题取首条用户消息。

### 6.9 API 层 `src/api/`

- `app.py`：`create_app()` 挂载 5 个路由（统一 `/api/v1` 前缀）、首页 Web UI、
  `FastApiMCP`（暴露 `search_knowledge` / `answer_with_knowledge` / `get_index_status` 三个操作）、
  统一异常处理与 404 中间件。MCP 挂载在 `/mcp`。
- 路由与操作 ID：

| 方法 | 路径 | operation_id | 说明 |
|------|------|--------------|------|
| GET | `/api/v1/health` | `health_check` | 健康检查 |
| GET | `/api/v1/status` | `system_status` | 组件状态监控（L4） |
| POST | `/api/v1/retrieval/search` | `search_knowledge` | 语义搜索 |
| POST | `/api/v1/chat` | `answer_with_knowledge` | RAG 问答 |
| POST | `/api/v1/documents/index` | `start_index_task` | 异步索引（202 立即返回 task_id） |
| GET | `/api/v1/index/tasks/{id}` | `get_index_status` | 索引任务状态 |
| GET | `/api/v1/sessions` | `list_sessions` | 会话列表 |
| GET | `/api/v1/sessions/{id}` | `get_session` | 会话详情 |
| DELETE | `/api/v1/sessions/{id}` | `delete_session` | 删除会话 |

- `web.py`：单文件内嵌 Web UI（纯原生 HTML/CSS/JS，无前端构建），含暗色模式、
  会话侧栏、流式（聚合式）聊天、来源标注展示。
- `services/chat.py`：`chat_with_rag` 组装消息（含历史）→ 流式收集回答 →
  反序列化持久化 → 返回 `(answer, session_id, elapsed_ms)`。
- `services/indexing.py`：内存 `IndexTaskManager`（任务状态机
  pending→running→done/failed），通过 `run_in_executor` 把阻塞索引放到线程池，避免阻塞事件循环。

### 6.10 CLI 层 `src/cli/`

- **主 CLI**（`knowledge.py`，Typer）：`web / cli / serve / index / search / chat /
  project / design / map / status / doctor / lark / help`。
  - 全部命令支持 `--json` 结构化输出；错误码约定：0 OK / 1 error / 3 not found / 75 transient / 78 config。
  - `_PipelineEcho` 把摄取管道的 `echo_fn` 进度解析成 Rich 进度条（JSON 模式禁用）。
  - `_ensure_llm_api_key_if_needed`：LLM 相关命令首次运行且无 key 时交互式引导。
- **交互式控制台**（`console.py`）：后台**守护线程**预加载 Agent（`_load_agent_background`），
  Agent 依赖命令在加载完成前被拦截提示；`/` 斜杠命令 15 个（含 `/status` 状态监控，加载中即可用）；支持 prompt_toolkit 补全。
- **遗留 Click CLI**（`commands.py` / `kb.py`）：旧版 `ingest/update/rebuild/add/chat/mode` 等，
  经 `main.py kb` / `main.py knowledge` 调用，与新 CLI 并存。

### 6.11 飞书机器人 `src/feishu/`

- 独立进程，`lark-oapi` **长连接（WebSocket）模式**，无需公网 URL。
- 文本消息转发到 `KB_API_BASE/api/v1/chat`，每个用户独立会话（`/new` 重置），
  `session_map.py` 将 `open_id→session_id` 持久化到 `data/feishu_sessions.json`。

---

## 7. 关键数据流

### 7.1 文档摄取（索引）

```
knowledge index ./docs  /  /add  /  API POST /documents/index
  → 复制到 data/external/（重名自动改名，忽略图片）
  → loader 加载（md/txt/pdf/代码/hdev）
  → knowledge_extract 知识化（.hdev/代码 → Markdown 知识文本）
  → splitter 切分（chunk_size=500, overlap=80）
  → _inject_capability_metadata（能力域/场景/技术标签）
  → Chroma 批量写入 + 重建 BM25 索引（磁盘缓存）
  → 知识图谱增量合并（jieba 或 LLM，LLM 失败降级 jieba）
  → update_tracker（file_tracker.json 记录哈希，用于增量/去重）
  → invalidate_retriever_cache()（索引版本 +1）
```

### 7.2 问答（核心链路）

```
knowledge chat "问题" / Web / API / MCP / 飞书
  → chat_with_rag(query, session_id)
      → 加载历史（JSON）+ 追加用户消息
      → QueryRouter（本地确定性规则，不额外调用分类 LLM）
          ├─ DIRECT：普通对话/通用问答/文本处理
          │    └─ 复用 LLM 直接流式回答；不构建 Agent、不检索、不做 LLM 历史摘要
          └─ AGENT：知识库/来源/工业视觉/外部最新资料
      → create_rag_agent() 或复用 ResourceManager 缓存
      → agent.stream({"messages": [...]})  ← Deep Agent（仅 AGENT 路径）
          ├─ 调用 retrieve_knowledge(query)
          │    ├─ 复用 ResourceManager 的 Retriever，不重复读取/构建 RAG 文件索引
          │    ├─ 混合检索：Chroma MMR + BM25 → Ensemble(0.5, 0.5)
          │    ├─ 并发 LLM 评分过滤（全不相关 → 查询重写再检索）
          │    ├─ 并发 LLM 上下文压缩（保留事实/来源）
          │    ├─ 相同查询复用检索/评分/压缩缓存；并发相同查询合并为一次执行
          │    ├─ 索引或模型配置变化后递增版本并自动使缓存失效
          │    └─ 知识图谱检索结果拼接（可选）
          ├─ 调用 project_workflow / retrieve_graph / 外部 MCP 工具（按需）
          └─ LLM 生成回答（标注 [来源: 文件名]）
      → 流式收集回答 → 保存会话历史（JSON）
      → 返回 answer + conversation_id
  → API 层 _extract_citations 正则提取来源 → citations 字段
```

### 7.3 方案生成（`knowledge design`）

```
project_desc（一句话需求）
  1. analyze_requirement：1 次 LLM → 结构化字段（product/task/target/.../unknown）
  2. select_algorithm_llm：规则表 + cap4 检索 + 1 次 LLM 算子细化
  3. generate_solution：按 10 章节分别从能力域 1/3/4/5/6 检索知识 + 1 次 LLM
  4. write_report：落盘 data/projects/<name>/ 的 5 个 Markdown
  5. （可选 --llm-check）方案质量/风险/完整性检查 → check_report.md
  6. log_llm_call：脱敏审计日志 llm_log.jsonl
```

---

## 8. 配置体系

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `KNOWLEDGE_HOME` | 项目根（开发）/ 平台应用数据目录（wheel） | 数据根目录（决定 `.env`、数据路径） |
| `DATA_DIR` / `EXTERNAL_DIR` | `./data/docs` / `./data/external` | 内部/外部文档目录 |
| `CHROMA_PERSIST_DIR` | `./chroma_db` | 向量库（含 BM25 缓存） |
| `GRAPH_PERSIST_DIR` | `./data` | 知识图谱 JSON 位置 |
| `EMBEDDING_MODEL` | `bge-small-zh` | bge-small-zh / bge-m3 / bge-base-zh / openai |
| `EMBEDDING_DEVICE` | `auto` | auto/cpu/cuda |
| `CHUNK_SIZE` / `CHUNK_OVERLAP` | 500 / 80 | 切分参数 |
| `TOP_K` | 5 | 检索数量 |
| `LLM_MODEL` | `deepseek-chat` | 主模型 |
| `DEEPSEEK_API_BASE` / `DEEPSEEK_API_KEY` | 官方 | 必填 |
| `RERANK_LLM` | `deepseek` | 评分/压缩用模型；`local` 切 Ollama |
| `LOCAL_LLM_BASE` / `LOCAL_LLM_MODEL` | 11434 / qwen3.5:4b | Ollama 端点 |
| `MCP_CONFIG_PATH` | `<HOME>/mcp.json` | 外部 MCP 配置 |
| `MCP_ENABLED` | `true` | 外部 MCP 总开关；Web 设置页可热切换 |
| `ENABLE_*` | 全开 | grading/rewrite/hybrid_search/context_compression/graph 开关 |
| `ENABLE_GRAPH_LLM_EXTRACTION` | false | 图谱抽取模式（jieba/LLM） |
| `MAX_CONTEXT_TOKENS` | 1000 | 压缩后上下文上限 |
| `CHAT_HISTORY_DIR` / `FILE_TRACKER_PATH` | 锚定 KNOWLEDGE_HOME | 会话/追踪文件覆盖 |
| `FEISHU_*` / `KB_API_BASE` | — | 飞书机器人 |

---

## 9. 运行时数据目录

```
<KNOWLEDGE_HOME>/
├── .env                      # 配置
├── chroma_db/                # Chroma 向量库 + bm25_index.pkl
├── data/
│   ├── docs/                 # 内部源文档
│   ├── external/             # knowledge index /add 导入的资料
│   ├── chat_history/         # 会话 JSON
│   ├── projects/             # design 生成的方案文档
│   ├── file_tracker.json     # 增量追踪哈希
│   ├── feishu_sessions.json  # 飞书用户会话映射
│   └── knowledge_graph.json  # 知识图谱
└── mcp.json                  # 外部 MCP 配置
```

> `data/`、`chroma_db/`、`.env` 均在 `.gitignore` 中排除。

---

## 10. 测试体系

- 框架：pytest，`tests/` 下 480 个测试（30+ 个测试文件，含 `test_status_monitoring.py`
  监控层测试与 `test_monitor.py` 监控修复程序测试）。
- 全覆盖的子系统：API 路由（REST + MCP 暴露 + Web 落地页）、CLI（Typer/Click/console/入口）、
  摄取（索引行为、去重、知识化、进度输出）、检索（混合/BM25/图谱）、会话、方案生成、
  项目工作流、飞书机器人、配置与路径解析、生命周期/关闭清理、初始化效率等。
- 外部服务（DeepSeek/HuggingFace）在测试中大多被 mock；另有 `tests/snapshots/` 用于
  CLI JSON 输出快照（syrupy）。
- 运行：`python -m pytest tests/`（全局 Python 3.13；`kb_env` 中无 pytest）。

---

## 11. 设计决策与工程约束

1. **知识按能力组织而非按来源**：检索粒度 = 能力域，来源仅作辅助元数据（映射规则零成本，无 LLM）。
2. **Agent 无状态 + 全局缓存**：Agent 跨请求复用（消息逐次传入），避免重复初始化 embedding/Chroma。
3. **重资源启动顺序固定**：embedding → LLM → Chroma → 图谱 → BM25，且 **agent 内先加载 embedding 再建 agent**
   （HuggingFace/httpx 客户端线程安全约束，见 AGENTS.md）。
4. **优雅降级**：外部 MCP 加载失败不影响本地工具；LLM 图谱抽取失败降级 jieba；
   评分/压缩/重写失败回退原始结果；PDF/XML 解析失败回退原文。
5. **阻塞工作不占事件循环**：索引任务经 `run_in_executor` 丢线程池；异步任务跟踪与关闭清理。
6. **数据变更即失效**：索引后 `invalidate_retriever_cache()`（BM25/Ensemble 缓存 + 版本号）。
7. **路径/密钥规范**：无硬编码绝对路径；相对路径锚定 `KNOWLEDGE_HOME`；密钥仅经 `.env`/环境变量。
8. **编码健壮性**：stdout 强制 UTF-8/replace；进度输出保持 ASCII；Windows 中文化路径需
   `CHROMA_PERSIST_DIR` 指到 ASCII 绝对路径。
9. **错误协议化**：CLI 统一 `--json` 输出 + 语义化错误码；API 统一 `ErrorResponse` + 全局异常处理。

---

## 12. 已知限制与改进空间

| 领域 | 现状 | 改进方向 |
|------|------|----------|
| 搜索 API | `/retrieval/search` 仅纯向量检索 | 与 CLI 一致接入混合检索 + 能力域过滤 |
| 会话压缩 | 简单摘要 + 保留最近 10 轮 | 分块摘要/多级记忆 |
| 图谱检索 | 子串匹配 + BFS 子图 | 实体归一化、embedding 化的图谱查询 |
| 图谱持久化 | 全量 JSON 重写 | 分片/增量 diff |
| 索引任务 | 内存态（重启丢失） | 持久化任务队列 + 分布式锁 |
| 评分/压缩 | 逐文档串行批内并发 | 批量 prompt 减少 LLM 调用 |
| Web 会话 | 聚合式回答 | SSE 流式输出 |
| 多用户 | 单机单知识库 | 多租户隔离（能力域可作为软隔离） |

---

## 附：入口速查

```bash
knowledge web          # Web UI + API + MCP（127.0.0.1:8000）
knowledge cli          # 交互式控制台（/help 查看命令）
knowledge search "q"   # 检索（--capability 4 过滤）
knowledge chat "q"     # RAG 问答
knowledge project "p" --stage 方案设计
knowledge design "p"   # 生成方案到 data/projects/
knowledge index <path> # 索引
knowledge map          # 能力模型与知识覆盖
knowledge status       # 状态
knowledge doctor       # 健康检查
knowledge lark         # 飞书机器人
python main.py         # 遗留入口（console / api / kb / knowledge）
```
