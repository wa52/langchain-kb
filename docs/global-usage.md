# 全局命令行使用

`knowledge` 是一个可在任意目录运行的全局命令。安装一次后，无需进入项目文件夹即可使用个人知识库的全部能力。

## 安装

```powershell
pip install -e <项目路径>
```

安装后验证：

```powershell
knowledge --help
```

> 用 `-e`（editable）安装，项目代码更新后无需重新安装。

## 常用命令

| 命令 | 作用 |
|------|------|
| `knowledge web` | 启动 Web 服务（首页 + API 文档 + MCP），`--open` 自动打开浏览器 |
| `knowledge cli` | 进入交互式问答控制台 |
| `knowledge search "问题"` | 检索知识片段 |
| `knowledge chat "问题"` | 基于知识库回答 |
| `knowledge index <路径>` | 索引文件或目录到向量库 |
| `knowledge status` | 查看系统状态（含当前数据目录） |
| `knowledge doctor` | 健康检查 |
| `knowledge serve` | 底层 API + MCP 服务入口（与 `web` 相同，无浏览器选项） |
| `knowledge help [命令]` | 显示帮助 |

所有命令支持 `--json` 结构化输出（交互式 `cli`、`help` 除外），`--color=always|auto|never` 控制颜色。

## 数据目录（KNOWLEDGE_HOME）

`.env`、`chroma_db/`、`data/`（外置数据、知识图谱）都存放在 **知识库目录** 中。默认是项目根目录，也可以用环境变量 `KNOWLEDGE_HOME` 指定：

```powershell
$env:KNOWLEDGE_HOME = "D:\KnowledgeBase"
knowledge web
```

`KNOWLEDGE_HOME` 必须作为 **环境变量** 设置，它决定了 `.env` 从哪个目录读取——因此不能写在 `.env` 里。其余路径（如 `CHROMA_PERSIST_DIR`、`EXTERNAL_DIR`、`DATA_DIR`）可以在 `.env` 中配置，相对路径都会基于 `KNOWLEDGE_HOME` 解析。

首次运行会自动创建目录骨架：`chroma_db/`、`data/docs/`（源文档目录）、`data/external/`（外置数据）。

> 源文档目录 `DATA_DIR` 默认是 `<KNOWLEDGE_HOME>/data/docs`，随知识库一起迁移，通常无需配置。只有当你的文档放在别处时，才在 `.env` 中设置 `DATA_DIR` 指向它。

从任意目录运行都会读取同一份 `KNOWLEDGE_HOME` 下的 `.env` 和数据，不会写入当前 shell 所在目录。

### 迁移到另一台电脑

1. 复制整个知识库目录（含 `chroma_db/`、`data/`）到目标电脑，例如通过 GitHub、U 盘或同步盘。
2. 在目标电脑安装命令：`pip install -e <项目路径>`。
3. 设置 `KNOWLEDGE_HOME` 指向复制过来的目录。
4. 零配置即可使用：目录骨架会自动创建。若源文档放在别处，再在 `.env` 中设置 `DATA_DIR`。

## 远程访问

只在一台机器上运行服务，其他设备通过浏览器访问同一个知识库：

```powershell
knowledge web --host 0.0.0.0 --port 8000
```

其他设备访问 `http://<主机IP>:8000/`，无需安装模型或本地索引。

> 注意：`--host 0.0.0.0` 会暴露在局域网（或公网）上。请仅在可信网络中使用，或通过反向代理 / VPN 保护。
