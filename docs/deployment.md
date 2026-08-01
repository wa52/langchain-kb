# 打包与部署

本文说明如何把 `personal-knowledge-base` 打包分发到另一台机器并运行起来。

## 一、打包

项目使用 `setuptools` + `pyproject.toml`，生成标准 wheel：

```powershell
# 在项目根目录
pip install build
python -m build        # 生成 dist/personal_knowledge_base-1.0.0-py3-none-any.whl
```

或直接安装到当前环境：

```powershell
pip install .          # 正式安装（生成 wheel 后安装）
pip install -e .       # 可编辑安装（开发用，代码改动即时生效）
```

安装后注册全局命令 `knowledge`（由 `pyproject.toml` 的 `[project.scripts]` 定义）。

> 打包内容包含 `config.py` 和 `src/` 包，入口为 `src.cli.entry:main`。验证：`knowledge --help` 应显示全部 9 个命令。

## 二、目标机器运行 Checklist

### 1. 安装 Python 与依赖

- 安装 Python ≥ 3.10
- 安装项目：`pip install <wheel 或项目路径>`
- 依赖会自动安装（`requirements.txt` 已声明，含 `langchain-classic`）

### 2. 准备知识库目录

所有数据（`.env`、`chroma_db/`、`data/`）集中在一个**知识库目录**。

`KNOWLEDGE_HOME` 的解析优先级：

1. **环境变量 `KNOWLEDGE_HOME`**（推荐显式设置）：`$env:KNOWLEDGE_HOME = "D:\KnowledgeBase"`
2. **wheel 安装**（config.py 位于 site-packages）：默认用**当前工作目录**——在哪运行就在哪建数据，装完即可用
3. **开发模式**（源码目录运行）：默认用项目根目录

`KNOWLEDGE_HOME` 决定 `.env` 从哪读取、相对路径如何解析。首次运行 `ensure_data_dirs()` 会自动创建目录骨架。

### 3. 配置 `.env`

在 `KNOWLEDGE_HOME` 下创建 `.env`：

```ini
DEEPSEEK_API_KEY=你的key
DEEPSEEK_API_BASE=https://api.deepseek.com
HF_ENDPOINT=https://huggingface.co
```

- `DEEPSEEK_API_KEY`：必填。若未配置，运行 `knowledge chat/web/serve/cli` 时会交互提示输入（仅交互终端），并自动写入 `.env`
- `HF_ENDPOINT`：建议 `https://huggingface.co`（`hf-mirror.com` 已失效，见 AGENTS.md）
- 路径含中文时，额外设置 `CHROMA_PERSIST_DIR` 为 ASCII 绝对路径（ChromaDB 在 Windows 的已知限制）

### 4. 预下载 embedding 模型（可选但推荐）

首次启动加载 embedding 模型 `BAAI/bge-small-zh-v1.5`（约 33MB）时会联网下载。可提前缓存避免首次启动等待：

```powershell
hf download BAAI/bge-small-zh-v1.5
```

缓存位于 `%USERPROFILE%\.cache\huggingface\hub`。离线环境可用 `HF_HUB_OFFLINE=1` 强制仅用缓存。

### 5. 数据迁移（可选）

如需保留已有知识库，把整个知识库目录（含 `chroma_db/`、`data/`）复制到目标机，并设置 `KNOWLEDGE_HOME` 指向它即可，零额外配置。

## 三、路径解析规则

| 数据 | 默认位置 | 说明 |
|------|---------|------|
| `.env` | `<KNOWLEDGE_HOME>/.env` | 配置来源 |
| 向量库 | `<KNOWLEDGE_HOME>/chroma_db` | `CHROMA_PERSIST_DIR` 可覆盖 |
| 源文档 | `<KNOWLEDGE_HOME>/data/docs` | `DATA_DIR` 可覆盖 |
| 外置数据 | `<KNOWLEDGE_HOME>/data/external` | `EXTERNAL_DIR` 可覆盖 |
| 会话历史 | `<KNOWLEDGE_HOME>/data/chat_history` | `CHAT_HISTORY_DIR` 可覆盖 |
| 文件追踪 | `<KNOWLEDGE_HOME>/data/file_tracker.json` | `FILE_TRACKER_PATH` 可覆盖 |
| 知识图谱 | `<KNOWLEDGE_HOME>/data` | `GRAPH_PERSIST_DIR` 可覆盖 |

所有相对路径均基于 `KNOWLEDGE_HOME` 解析，与当前工作目录无关——从任意目录运行 `knowledge` 命令都会读写同一份数据。

## 四、验证部署

```powershell
knowledge doctor       # 健康检查：配置/模型/向量库/依赖
knowledge status       # 系统状态：向量数/来源/BM25/端口
knowledge search "测试"  # 确认检索可用
knowledge chat "你好"    # 确认问答可用（需 DeepSeek key）
```

## 五、常见问题

- **`knowledge` 命令找不到**：未安装或 `pip install -e .` 从错误目录安装。重新 `pip install .`
- **中文路径报错**：设置 ASCII 的 `CHROMA_PERSIST_DIR`
- **启动卡在下载模型**：网络受限，按第 4 步预下载模型，或用 `HF_ENDPOINT` 指向可用镜像
- **`ModuleNotFoundError: src`**：wheel 安装不完整或从错误 CWD 运行，重新 `pip install .`
