# 飞书机器人接入

把知识库 RAG Agent 接入飞书机器人：用户在飞书里给机器人发文本消息，
机器人调用知识库 `POST /api/v1/chat` 并回复答案。每个飞书用户按
`open_id` 各自延续对话历史，发送 `/new` 重置会话。

采用官方 SDK `lark-oapi` 的**长连接（WebSocket）模式**，机器人主动与
飞书建立连接，**不需要公网 URL / ngrok**。

## 架构

```
飞书 App ──长连接──> src/feishu/bot.py（独立进程）
                         │  POST http://127.0.0.1:8000/api/v1/chat
                         ▼
              API 服务（serve.bat，FastAPI + RAG Agent）
                         ▲
                 data/feishu_sessions.json（open_id -> session_id）
```

- 机器人进程很薄：只依赖 `lark-oapi` + `httpx`，通过 HTTP 调知识库 API。
- 会话记忆按飞书用户 `open_id` 映射到知识库 `session_id`，持久化在
  `data/feishu_sessions.json`。
- 群聊中用户需 `@机器人` 后提问；机器人用「引用回复」回答。

## 1. 飞书开放平台配置

1. [open.feishu.cn](https://open.feishu.cn/app) → **创建企业自建应用**。
2. **凭证与基础信息**：拿到 `App ID`（形如 `cli_xxx`）和 `App Secret`。
3. **添加应用能力 → 机器人**：启用机器人。
4. **事件订阅**：接收方式选 **长连接（WebSocket）**（不要填请求网址 URL），
   添加事件 `im.message.receive_v1`（接收消息）。
5. **权限管理** 开通：
   - `im:message`（获取与发送单聊、群组消息）
   - `im:message.p2p_msg:readonly`（获取用户发给机器人的单聊消息）
   - `im:message.group_at_msg:readonly`（获取群组中@机器人的消息）
6. **版本管理与发布**：创建版本并发布（或用「测试企业与人员」免发布测试）。

## 2. 配置 .env

在项目根目录 `.env`（参考 `.env.example`）追加：

```ini
FEISHU_APP_ID=cli_xxxxxxxxxxxxxxxx
FEISHU_APP_SECRET=xxxxxxxxxxxxxxxxxxxxxxxx
KB_API_BASE=http://127.0.0.1:8000
```

## 3. 安装依赖并启动

```powershell
kb_env\Scripts\pip install -r requirements.txt   # 首次：安装 lark-oapi
```

两个终端，先起 API 服务，再起机器人：

```powershell
# 终端 1：API 服务（约 40s 就绪，健康检查返回 200）
.\serve.bat

# 终端 2：飞书机器人
kb_env\Scripts\python -m src.feishu.bot
# 或已安装 CLI： knowledge lark
```

机器人启动后日志显示 `Feishu bot connecting via long connection ...`，
即可在飞书里搜索机器人名称并发送消息体验。

## 使用说明

- 发文本消息 → 知识库回答（带 `[来源: ...]` 引用）。
- 发 `/new`（或 `/新会话`）→ 清空该用户会话历史，重新开始。
- 发非文本消息 → 提示「仅支持文本消息」。

## 说明与限制

- 机器人进程需要 API 服务在同一机器可达（默认 `127.0.0.1:8000`，
  可用 `KB_API_BASE` 覆盖）。
- 长连接模式无需公网 URL；如改用 Webhook 模式，需提供公网请求网址并
  在 `.env` 配置 `ENCRYPT_KEY` / `VERIFICATION_TOKEN`。
- 会话按用户 `open_id` 隔离；群聊内多人提问各有各的上下文。
