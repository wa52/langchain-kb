# Knowledge CLI — Typer + Rich 设计

## Command Tree

```
knowledge
├── serve                    启动 API + MCP 服务
│   ├── --host TEXT        (默认 127.0.0.1)
│   ├── --port INTEGER     (默认 8000)
│   └── --json
├── index PATH               索引文件或目录
│   ├── --incremental      增量模式
│   ├── --force            强制重建
│   └── --json
├── search QUERY             检索知识片段
│   ├── --top-k INTEGER    (默认 5)
│   ├── --json
│   └── --plain
├── chat QUESTION            基于知识库回答
│   ├── --session TEXT
│   └── --json
├── status                   查看系统状态
│   └── --json
└── doctor                   健康检查
    ├── --verbose
    └── --json
```

## Output Discipline

| 流 | 内容 |
|----|------|
| stdout | 数据：Rich 表格/Panel/Markdown，或纯 JSON |
| stderr | 日志、进度条、错误、spinner |

- `--json` 模式：`print(json.dumps(payload))` 直出，**禁止** Rich 渲染、颜色、进度、额外文本。
- 非 TTY：Rich 自动关闭动画与颜色（`Console` 检测 `isatty`）。
- `NO_COLOR` 环境变量：Rich 原生遵守。
- 进度条（`Progress`）绑定 stderr console。
- 不固定终端宽度；表格自动适应。

## JSON Envelope

```json
{"status": "ok", "data": {...}}
{"status": "error", "error": {"code": "NOT_FOUND", "message": "..."}}
```

## Exit Codes

| 码 | 含义 |
|----|------|
| 0  | 成功 |
| 1  | 一般失败 |
| 2  | 用法错误（Typer 自动） |
| 3  | 资源不存在（index 路径） |
| 75 | 瞬时失败（serve 端口被占） |
| 78 | 配置错误（doctor 缺 API key） |

## UI Sketches

见上方回复；`index` 使用 `rich.progress.Progress` 将 pipeline 的
`echo_fn` 阶段消息 + 百分比转成 Rich 进度条（stderr），`--json` 时 echo 为 no-op。
