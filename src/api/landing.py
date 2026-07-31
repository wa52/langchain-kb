from config import PRODUCT_NAME, PRODUCT_NAME_EN


def landing_html() -> str:
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{PRODUCT_NAME}</title>
<style>
  :root {{ color-scheme: light dark; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    background: #f6f7f9; color: #1f2328; line-height: 1.6;
    display: flex; min-height: 100vh; align-items: center; justify-content: center; padding: 32px 16px;
  }}
  .card {{
    background: #fff; border: 1px solid #e2e5ea; border-radius: 12px;
    box-shadow: 0 8px 30px rgba(0,0,0,.06); max-width: 640px; width: 100%; padding: 40px;
  }}
  h1 {{ font-size: 26px; font-weight: 700; }}
  .sub {{ color: #59636e; margin: 8px 0 24px; }}
  .links {{ display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 28px; }}
  a.btn {{
    text-decoration: none; padding: 10px 16px; border-radius: 8px; font-size: 14px;
    background: #0969da; color: #fff; transition: background .15s;
  }}
  a.btn:hover {{ background: #0550ae; }}
  h2 {{ font-size: 15px; margin: 20px 0 8px; color: #1f2328; }}
  pre {{
    background: #0d1117; color: #e6edf3; border-radius: 8px; padding: 14px 16px;
    font-size: 13px; overflow-x: auto; margin-bottom: 8px;
  }}
  code {{ font-family: "Cascadia Code", Consolas, monospace; }}
  .muted {{ color: #59636e; font-size: 13px; }}
  @media (prefers-color-scheme: dark) {{
    body {{ background: #0d1117; color: #e6edf3; }}
    .card {{ background: #161b22; border-color: #30363d; }}
    h2 {{ color: #e6edf3; }}
    .sub, .muted {{ color: #8b949e; }}
    pre {{ background: #010409; }}
  }}
</style>
</head>
<body>
  <div class="card">
    <h1>{PRODUCT_NAME}</h1>
    <p class="sub">基于检索增强生成（RAG）的{PRODUCT_NAME_EN}服务，聚合语义检索、知识图谱与对话问答。</p>
    <div class="links">
      <a class="btn" href="/docs">API 文档</a>
      <a class="btn" href="/mcp">MCP 服务</a>
      <a class="btn" href="/api/v1/health">健康检查</a>
    </div>
    <h2>快速开始</h2>
    <pre><code>python main.py knowledge serve</code></pre>
    <p class="muted">启动后访问本页即可使用上述入口。</p>
  </div>
</body>
</html>
"""
