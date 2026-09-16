# Knowledge Agent Web 客户端 UI 设计规格

> 适用范围：第一阶段 `web/` 前端工程（Vite + React + TypeScript）。
> 本文定义产品界面、交互规则和状态展示规范；系统架构见 `docs/architecture.md`。

## 1. 产品界面定位

本项目的 Web UI 是 **本地单用户 Knowledge Agent 客户端**，不是后台管理系统。

核心目标：

- 让用户通过一个干净的 Chat 工作台使用 Knowledge Agent。
- 让用户看清知识库和系统是否可用。
- 让用户能添加资料、查看状态、获得修复建议。
- 避免按钮、表单和运维控件堆叠。

界面气质：工程诊断台，而不是通用聊天站点或管理后台。视觉上强调状态清晰、低干扰、信息密度适中。

## 2. UI 原则

### 2.1 不堆叠控件

硬性规则：

- 每个页面最多暴露 1 个主操作。
- 一个页面同时出现超过 3 个按钮时，必须重新设计。
- 次级操作放进详情、抽屉、更多菜单或异常项展开区。
- 危险操作必须进入确认流程。
- 修复动作只在对应异常项详情中出现，不能常驻铺满状态页。

示例：

| 场景 | 推荐 | 避免 |
|------|------|------|
| Chat | 输入框 + 发送/停止 | 同时放搜索、索引、诊断、配置按钮 |
| Status | 一个“运行完整诊断”主操作 | 每个组件后面放重建/刷新/修复按钮 |
| Knowledge | 一个“添加资料”主操作 | 卡片上堆删除、重建、刷新、同步按钮 |
| Settings | 只读配置状态 + 指引 | UI 中直接编辑全部 `.env` |

### 2.2 状态驱动操作出现

操作不应无条件展示，而应由状态触发：

- BM25 stale 时才展示“重建 BM25”。
- Graph 缺失时才展示“重建图谱”。
- LLM key 缺失时展示配置说明，不展示密钥输入框。
- 局域网模式未配置 token 时，启动阻止或状态页展示明确错误。

### 2.3 用户视角优先

默认文案回答用户关心的问题：

- 现在能不能聊天？
- 知识库有没有资料？
- 回答有没有引用来源？
- 哪个配置缺失？
- 我下一步该做什么？

开发者信息只能在轻量开发者模式中显示。

## 3. 信息架构

第一阶段采用 **单工作台、少导航**。

```
App Shell
├── Chat        # 默认主视图
├── Knowledge   # 轻量知识库概览
├── Status      # 轻量状态展示
└── Settings    # 只读配置状态
```

桌面端：左侧窄 rail + 顶部 System Rail + 主工作区。

```
┌──────────────────────────────────────────────┐
│ Product       System Rail              Menu  │
├──────┬───────────────────────────────────────┤
│ Rail │ Main Workspace                         │
│ Chat │                                       │
│ KB   │                                       │
│ Stat │                                       │
│ Set  │                                       │
└──────┴───────────────────────────────────────┘
```

移动端：顶部状态 + 主内容 + 底部 tabs。

```
┌────────────────────────────┐
│ Product + status           │
├────────────────────────────┤
│ Main view                  │
├────────────────────────────┤
│ Chat / KB / Status / Set   │
└────────────────────────────┘
```

## 4. App Shell

App Shell 只承载导航和状态，不承载业务表单。

顶部区域包含：

- 产品名。
- System Rail 状态链路。
- 一个全局菜单或设置入口。

System Rail：

```
embedding -> llm -> vector -> bm25 -> graph -> agent
```

状态表达：

| 状态 | 表现 |
|------|------|
| ready | 实心绿色状态点 |
| loading | 蓝色脉冲状态点 |
| error | 红色断点或红色状态点 |
| degraded | 黄色状态点 |
| disabled | 灰色状态点 |
| pending | 空心或弱灰状态点 |

点击 System Rail 进入 Status 页面。

## 5. Chat 页面

Chat 是默认主界面。

### 5.1 默认布局

默认不展示右侧详情面板。

```
┌────────────────────────────────────┐
│ Agent Ready · 110078 chunks         │
├────────────────────────────────────┤
│ Conversation                        │
│                                    │
│ Assistant answer                    │
│ Sources [file_a.md] [file_b.pdf]    │
│                                    │
├────────────────────────────────────┤
│ 输入问题...                 发送/停止 │
└────────────────────────────────────┘
```

### 5.2 消息规则

- 用户消息保持轻量，不抢占视觉。
- Agent 回答以正文为主。
- 来源默认显示 2-3 个 source chips。
- 更多来源用 `+N` chip 表示。
- 点击 source chip 打开来源详情抽屉。
- 工具调用过程默认不展示。

来源 chip 示例：

```
来源  [camera_calibration.md] [halcon_notes.pdf] [+3]
```

### 5.3 来源详情抽屉

点击来源后打开抽屉，不常驻右侧栏。

抽屉内容：

- 文件名。
- excerpt。
- chunk id。
- 命中链路：vector / bm25 / graph。
- 可复制引用。

不展示完整底层向量、prompt、API key 或原始 LLM response。

### 5.4 流式输出

Chat 流式接口采用 `POST + fetch readable stream`，事件使用 SSE 文本格式。

请求：

```http
POST /api/v1/chat/stream
Content-Type: application/json
Authorization: Bearer <token>  # 仅局域网模式需要
```

请求体：

```json
{
  "query": "...",
  "session_id": "...",
  "capability": null
}
```

第一阶段事件类型：

| 事件 | 说明 |
|------|------|
| `message_start` | 回答开始，创建 assistant 消息 |
| `token` | 增量文本 |
| `sources` | 来源列表，通常在结束前或结束时返回 |
| `message_end` | 回答结束，写入会话历史 |
| `error` | 流式错误 |

### 5.5 停止生成

第一阶段必须支持停止生成。

行为：

- 前端用 `AbortController` 中断当前 fetch stream。
- 输入框恢复可用。
- 当前 assistant 消息标记为“已停止生成”。
- 半截回答保存到会话历史，标记 `interrupted=true`。
- 如果来源尚未生成完成，显示“来源未完成”。

## 6. 空知识库体验

知识库为空时，不进入独立向导，仍显示 Chat 主界面，并融合空状态卡。

推荐文案：

```
知识库还没有资料

添加文档后，Agent 会基于你的资料回答问题、引用来源并关联图谱。

[添加资料]

也可以先直接聊天，但回答不会包含本地知识库引用。
```

只有一个主操作：“添加资料”。

## 7. Knowledge 页面

Knowledge 第一阶段是轻量知识库概览，不是完整文档管理后台。

展示内容：

- documents 数。
- chunks 数。
- BM25 sync 状态。
- graph entities / relations。
- 最近索引任务状态。
- 一个主操作：“添加资料”。

添加资料交互：

- 点击“添加资料”打开抽屉。
- 支持本地文件/目录路径。
- 支持 Web 拖拽上传文件。
- 上传文件保存到 `KNOWLEDGE_HOME/external/` 后进入统一 `IndexDocuments` 用例。

局域网模式提示：

```
本地路径读取的是运行服务的那台电脑上的路径；拖拽上传会保存到该电脑的数据目录。
```

第一阶段不做：

- 完整文档列表。
- 单文件删除。
- 批量重建按钮。
- 索引历史表格。
- URL 抓取、云盘同步、数据库连接。

## 8. Status 页面

Status 第一阶段是轻量状态页，不是完整诊断工作台。

页面结构：

```
Overall Status
  Ready / Degraded / Error / Loading

System Rail
  embedding -> llm -> vector -> bm25 -> graph -> agent

Key Metrics
  chunks / bm25 chunks / graph entities / index state

Issues
  当前问题列表 + 影响 + 建议动作

Primary Action
  运行完整诊断
```

规则：

- 默认只读。
- 只保留一个主操作：“运行完整诊断”。
- 自动修复动作只在异常项详情里出现。
- 不常驻展示所有日志、所有环境变量、所有后台任务控制按钮。

状态文案示例：

```
系统可用，但处于降级状态：
- LLM API Key 未配置，聊天功能不可用。
- 本地知识检索仍可使用。
- 请在 .env 中配置 DEEPSEEK_API_KEY 后重启服务。
```

```
知识库索引异常：
- Chroma chunk 数：110078
- BM25 chunk 数：109820
- BM25 缓存已过期。
- 展开此问题后可重建 BM25。
```

## 9. Settings 页面

Settings 第一阶段只读，不编辑配置文件。

展示内容：

- `KNOWLEDGE_HOME` 当前路径。
- 数据目录位置。
- LLM provider/model。
- API key configured: yes/no。
- Embedding model。
- HF offline mode。
- Chroma path 状态。
- Graph enabled: yes/no。
- MCP enabled: yes/no。
- LAN access protection: enabled/disabled。

安全规则：

- 不显示任何 API key、token、密码明文。
- 不在 UI 中直接编辑 `.env`。
- 配置变更通过清晰说明引导用户手动处理。

## 10. 会话历史

会话历史本地自动保存，UI 轻量展示。

规则：

- Chat 主界面不常驻大侧栏。
- 历史会话通过抽屉、弹层或 rail 入口打开。
- 支持恢复会话继续追问。
- 单用户本地数据，不做多人账号隔离。
- 中断的半截回答保存，并标记 `interrupted=true`。

## 11. Agent 权限与用户确认

Agent 可建议，不能直接执行改变知识库状态的操作。

| 操作 | Agent 权限 | UI 行为 |
|------|------------|---------|
| 检索知识 | 可直接执行 | 正常回答 |
| 查看轻量状态 | 可直接执行 | 可解释当前系统状态 |
| 添加资料 | 只能建议 | 打开 Knowledge 添加资料抽屉，由用户确认 |
| 删除资料 | 禁止直接执行 | 后续文档管理功能中显式确认 |
| 重建索引/修复 | 只能建议 | Status 异常项详情中显式确认 |
| 修改配置/密钥 | 禁止执行 | 指引用户手动修改配置 |

## 12. 开发者模式

第一阶段提供轻量开发者模式，默认关闭。

允许展示：

- SSE 连接状态。
- 本次回答耗时。
- sources 数量。
- 使用链路：vector / bm25 / graph。
- API 错误详情。
- `/api/status` 原始 JSON。

禁止默认展示：

- prompt 原文。
- API key / token。
- 完整 LLM raw response。
- 全量 retrieved chunks。
- 复杂 trace timeline。

## 13. 视觉 Token

第一阶段采用“视觉知识控制台”风格，避免通用后台灰白模板。

Light：

| Token | Value | 用途 |
|-------|-------|------|
| `--bg` | `#EEF3F7` | 页面背景 |
| `--panel` | `#FFFFFF` | 主面板 |
| `--ink` | `#16202A` | 主文字 |
| `--muted` | `#657282` | 次级文字 |
| `--signal-blue` | `#2563EB` | 主操作/活动状态 |
| `--laser-cyan` | `#00A6B8` | 状态链路强调 |
| `--pass-green` | `#1F9D55` | ready |
| `--warn-amber` | `#D97706` | degraded/warning |
| `--fail-red` | `#DC2626` | error |
| `--grid-line` | `#D7E0EA` | 分隔线 |

Dark：

| Token | Value | 用途 |
|-------|-------|------|
| `--bg` | `#0B1118` | 页面背景 |
| `--panel` | `#111A24` | 主面板 |
| `--panel-raised` | `#162231` | 抽屉/浮层 |
| `--ink` | `#E6EDF3` | 主文字 |
| `--muted` | `#8A98A8` | 次级文字 |
| `--signal-blue` | `#60A5FA` | 主操作/活动状态 |
| `--laser-cyan` | `#22D3EE` | 状态链路强调 |
| `--pass-green` | `#4ADE80` | ready |
| `--warn-amber` | `#FBBF24` | degraded/warning |
| `--fail-red` | `#F87171` | error |

字体：

```css
--font-ui: "Segoe UI", "Microsoft YaHei", "Noto Sans SC", sans-serif;
--font-mono: "Cascadia Code", "JetBrains Mono", Consolas, monospace;
```

不依赖外部字体 CDN，避免离线环境失败。

## 14. 可访问性与响应式

- 所有交互元素必须有可见 focus 状态。
- 状态变化区域使用 `aria-live`，但避免频繁刷屏。
- 支持 `prefers-reduced-motion`，loading 动效可关闭。
- 移动端主导航改为底部 tabs。
- 抽屉在移动端全屏展示。
- 状态颜色必须配合文字，不只靠颜色表达。

## 15. 第一阶段范围

必须做：

- App Shell + 极简导航。
- Chat 主界面。
- POST streaming SSE 客户端。
- 停止生成。
- 精简来源 chips + 来源详情抽屉。
- Chat + 空知识库融合空状态。
- Knowledge 轻量概览 + 添加资料入口。
- Status 轻量状态页 + System Rail。
- Settings 只读配置状态。
- 轻量开发者模式。

明确不做：

- 完整文档管理后台。
- 多用户账号系统。
- UI 中编辑 `.env`。
- 默认展示工具 trace。
- WebSocket。
- 系统托盘、Electron、Tauri。
- URL 抓取、云盘同步、数据库连接。
