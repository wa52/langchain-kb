from config import PRODUCT_NAME

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>__PRODUCT_NAME__</title>
<style>
  :root {
    color-scheme: light dark;
    --bg: #f6f7f9; --panel: #ffffff; --border: #e2e5ea;
    --fg: #1f2328; --muted: #59636e;
    --primary: #0969da; --primary-fg: #ffffff;
    --danger: #cf222e; --ok: #1a7f37;
    --ring: #0969da;
  }
  @media (prefers-color-scheme: dark) {
    :root {
      --bg: #0d1117; --panel: #161b22; --border: #30363d;
      --fg: #e6edf3; --muted: #8b949e;
      --primary: #4493f8; --primary-fg: #ffffff;
      --danger: #f85149; --ok: #3fb950;
      --ring: #4493f8;
    }
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    font-family: -apple-system, "Segoe UI", "Microsoft YaHei", sans-serif;
    font-size: 16px; line-height: 1.5;
    background: var(--bg); color: var(--fg);
  }
  a { color: var(--primary); }
  .topbar {
    display: flex; align-items: center; justify-content: space-between; gap: 12px;
    padding: 12px 16px; border-bottom: 1px solid var(--border);
    background: var(--panel); flex-wrap: wrap;
  }
  .brand { font-weight: 700; font-size: 17px; }
  nav { display: flex; gap: 12px; flex-wrap: wrap; }
  nav a { text-decoration: none; font-size: 14px; display: inline-flex; align-items: center; min-height: 44px; padding: 0 4px; }
  .layout {
    display: grid; grid-template-columns: 1fr; gap: 16px;
    max-width: 1200px; margin: 0 auto; padding: 16px;
  }
  @media (min-width: 860px) {
    .layout { grid-template-columns: minmax(0, 1fr) 380px; align-items: start; }
  }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
  }
  .panel h2 { font-size: 15px; margin-bottom: 12px; }
  .side { display: grid; grid-template-columns: 1fr; gap: 16px; }
  .row { display: flex; gap: 8px; }
  input[type="text"] {
    flex: 1; min-width: 0; min-height: 44px;
    padding: 0 12px; font-size: 15px;
    border: 1px solid var(--border); border-radius: 8px;
    background: var(--bg); color: var(--fg);
  }
  button {
    min-height: 44px; min-width: 44px;
    padding: 0 16px; font-size: 15px; cursor: pointer;
    border: 1px solid transparent; border-radius: 8px;
    transition: background .15s ease, opacity .15s ease;
    background: var(--primary); color: var(--primary-fg);
  }
  button:disabled { opacity: .55; cursor: not-allowed; }
  button:not(:disabled):hover { filter: brightness(1.08); }
  :focus-visible { outline: 3px solid var(--ring); outline-offset: 2px; }
  .out { margin-top: 12px; }
  .msg { margin-bottom: 10px; }
  .msg .who { font-size: 12px; color: var(--muted); margin-bottom: 2px; }
  .msg .body { white-space: pre-wrap; word-break: break-word; }
  .msg.user .body { background: var(--bg); border: 1px solid var(--border); border-radius: 8px; padding: 8px 12px; }
  .citation { font-size: 13px; color: var(--muted); }
  .result {
    border: 1px solid var(--border); border-radius: 8px;
    padding: 8px 12px; margin-bottom: 8px;
  }
  .result .src { font-weight: 600; font-size: 14px; }
  .result .meta { font-size: 12px; color: var(--muted); margin: 2px 0 6px; }
  .result .content { font-size: 14px; white-space: pre-wrap; word-break: break-word; }
  .status { font-size: 14px; margin-top: 8px; }
  .status.err { color: var(--danger); }
  .status.ok { color: var(--ok); }
  .status.busy { color: var(--muted); }
  .empty { color: var(--muted); font-size: 14px; }
  .hint { color: var(--muted); font-size: 12px; margin-top: 8px; }
  footer {
    max-width: 1200px; margin: 0 auto; padding: 8px 16px 24px;
    color: var(--muted); font-size: 13px; line-height: 1.8;
  }
  code { font-family: "Cascadia Code", Consolas, monospace; background: var(--bg);
         border: 1px solid var(--border); border-radius: 4px; padding: 0 4px; }
  @media (prefers-reduced-motion: reduce) {
    * { transition: none !important; animation: none !important; }
  }
</style>
</head>
<body>
  <header class="topbar">
    <div class="brand">__PRODUCT_NAME__</div>
    <nav>
      <a href="/docs">API 文档</a>
      <a href="/mcp">MCP</a>
      <a href="/api/v1/health">健康检查</a>
    </nav>
  </header>

  <main class="layout">
    <section class="panel" id="chat-view" aria-labelledby="chat-title">
      <h2 id="chat-title">问答</h2>
      <form id="chat-form" class="row">
        <input id="chat-input" type="text" placeholder="输入问题…" autocomplete="off" required aria-label="问题">
        <button type="submit">发送</button>
      </form>
      <div class="out" id="chat-log" aria-live="polite" aria-busy="false"></div>
      <p class="hint" id="chat-hint">基于知识库检索增强生成，可连续追问。</p>
    </section>

    <aside class="side">
      <section class="panel" id="search-view" aria-labelledby="search-title">
        <h2 id="search-title">检索</h2>
        <form id="search-form" class="row">
          <input id="search-input" type="text" placeholder="输入检索词…" autocomplete="off" required aria-label="检索词">
          <button type="submit">检索</button>
        </form>
        <div class="out" id="search-results" aria-live="polite" aria-busy="false"></div>
      </section>

      <section class="panel" id="index-view" aria-labelledby="index-title">
        <h2 id="index-title">索引</h2>
        <form id="index-form" class="row">
          <input id="index-path" type="text" placeholder="文件或目录路径…" autocomplete="off" required aria-label="文件或目录路径">
          <button type="submit">索引</button>
        </form>
        <div class="out" id="index-status" aria-live="polite" aria-busy="false"></div>
        <p class="hint">输入服务器上的文件或目录路径，提交后自动轮询任务进度。</p>
      </section>
    </aside>
  </main>

  <footer>
    命令行入口：<code>knowledge web</code> <code>knowledge cli</code> <code>knowledge search "问题"</code> · 安装：<code>pip install -e &lt;项目路径&gt;</code>
  </footer>

<script>
(function () {
  "use strict";

  function escapeHtml(text) {
    var div = document.createElement("div");
    div.textContent = String(text == null ? "" : text);
    return div.innerHTML;
  }

  async function postJSON(url, body) {
    var resp = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    var data = null;
    try { data = await resp.json(); } catch (e) { /* ignore */ }
    if (!resp.ok) {
      var detail = data && (data.detail || data.error);
      throw new Error(detail || ("请求失败 (" + resp.status + ")"));
    }
    return data;
  }

  function setBusy(el, busy, button) {
    el.setAttribute("aria-busy", busy ? "true" : "false");
    if (button) button.disabled = busy;
  }

  function clearOutput(el) { el.innerHTML = ""; }

  // ---------- 问答 ----------
  var chatForm = document.getElementById("chat-form");
  var chatInput = document.getElementById("chat-input");
  var chatLog = document.getElementById("chat-log");
  var chatHint = document.getElementById("chat-hint");
  var chatButton = chatForm.querySelector("button");
  var sessionId = null;

  chatForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = chatInput.value.trim();
    if (!q) return;
    chatInput.value = "";
    chatHint.hidden = true;
    appendChat("user", escapeHtml(q));
    var statusEl = appendChat("status", "正在思考…");
    setBusy(chatLog, true, chatButton);
    postJSON("/api/v1/chat", { query: q, session_id: sessionId })
      .then(function (data) {
        sessionId = data.conversation_id || null;
        statusEl.remove();
        var answer = (data.answer || "").replace(/\\[来源:[^\\]]*\\]/g, "").trim();
        appendChat("assistant", escapeHtml(answer));
        if (data.citations && data.citations.length) {
          var cites = data.citations.map(function (c) { return escapeHtml(c.source); })
            .filter(function (v, i, a) { return a.indexOf(v) === i; });
          appendChat("citations", "来源：" + cites.join(" · "));
        }
        if (typeof data.elapsed_ms === "number") {
          appendChat("status", "耗时 " + data.elapsed_ms.toFixed(0) + " ms");
        }
      })
      .catch(function (err) {
        statusEl.remove();
        appendChat("err", "回答失败：" + escapeHtml(err.message));
      })
      .finally(function () { setBusy(chatLog, false, chatButton); });
  });

  function appendChat(kind, html) {
    var div = document.createElement("div");
    div.className = "msg " + kind;
    var label = { user: "你", assistant: "助手", status: "", citations: "引用", err: "错误" }[kind] || "";
    if (label) {
      var who = document.createElement("div");
      who.className = "who";
      who.textContent = label;
      div.appendChild(who);
    }
    var body = document.createElement("div");
    body.className = "body";
    body.innerHTML = html;
    if (kind === "status") body.className = "status busy";
    if (kind === "err") body.className = "status err";
    if (kind === "citations") body.className = "citation";
    div.appendChild(body);
    chatLog.appendChild(div);
    chatLog.scrollTop = chatLog.scrollHeight;
    return body;
  }

  // ---------- 检索 ----------
  var searchForm = document.getElementById("search-form");
  var searchInput = document.getElementById("search-input");
  var searchResults = document.getElementById("search-results");
  var searchButton = searchForm.querySelector("button");

  searchForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var q = searchInput.value.trim();
    if (!q) return;
    clearOutput(searchResults);
    var statusEl = document.createElement("div");
    statusEl.className = "status busy";
    statusEl.textContent = "检索中…";
    searchResults.appendChild(statusEl);
    setBusy(searchResults, true, searchButton);
    postJSON("/api/v1/retrieval/search", { query: q, top_k: 5 })
      .then(function (data) {
        clearOutput(searchResults);
        var results = data.results || [];
        if (!results.length) {
          var empty = document.createElement("p");
          empty.className = "empty";
          empty.textContent = "未找到相关结果，换个关键词试试。";
          searchResults.appendChild(empty);
          return;
        }
        results.forEach(function (r) {
          var card = document.createElement("div");
          card.className = "result";
          card.innerHTML =
            '<div class="src">' + escapeHtml(r.source) + "</div>" +
            '<div class="meta">chunk ' + escapeHtml(r.chunk_id) +
            " · 分数 " + (typeof r.score === "number" ? r.score.toFixed(4) : escapeHtml(r.score)) + "</div>" +
            '<div class="content">' + escapeHtml(r.content) + "</div>";
          searchResults.appendChild(card);
        });
      })
      .catch(function (err) {
        clearOutput(searchResults);
        var errEl = document.createElement("p");
        errEl.className = "status err";
        errEl.textContent = "检索失败：" + err.message;
        searchResults.appendChild(errEl);
      })
      .finally(function () { setBusy(searchResults, false, searchButton); });
  });

  // ---------- 索引 ----------
  var indexForm = document.getElementById("index-form");
  var indexPath = document.getElementById("index-path");
  var indexStatus = document.getElementById("index-status");
  var indexButton = indexForm.querySelector("button");
  var pollTimer = null;

  indexForm.addEventListener("submit", function (e) {
    e.preventDefault();
    var p = indexPath.value.trim();
    if (!p) return;
    if (pollTimer) { clearInterval(pollTimer); pollTimer = null; }
    clearOutput(indexStatus);
    var statusEl = document.createElement("div");
    statusEl.className = "status busy";
    statusEl.textContent = "提交索引任务…";
    indexStatus.appendChild(statusEl);
    setBusy(indexStatus, true, indexButton);
    postJSON("/api/v1/documents/index", { path: p })
      .then(function (data) {
        statusEl.textContent = "任务已创建，等待处理…";
        pollTask(data.task_id, statusEl);
      })
      .catch(function (err) {
        statusEl.textContent = "索引失败：" + err.message;
        statusEl.className = "status err";
        setBusy(indexStatus, false, indexButton);
      });
  });

  function pollTask(taskId, statusEl) {
    pollTimer = setInterval(function () {
      fetch("/api/v1/index/tasks/" + encodeURIComponent(taskId))
        .then(function (resp) {
          if (!resp.ok) throw new Error("查询任务失败 (" + resp.status + ")");
          return resp.json();
        })
        .then(function (task) {
          var s = task.status;
          if (s === "done") {
            statusEl.textContent = "索引完成。";
            statusEl.className = "status ok";
            if (task.result) statusEl.textContent += " " + JSON.stringify(task.result);
            clearInterval(pollTimer); pollTimer = null;
            setBusy(indexStatus, false, indexButton);
          } else if (s === "failed") {
            statusEl.textContent = "索引失败：" + (task.error || "未知错误");
            statusEl.className = "status err";
            clearInterval(pollTimer); pollTimer = null;
            setBusy(indexStatus, false, indexButton);
          } else {
            statusEl.textContent = s === "pending" ? "等待处理…" : "索引中…";
            if (task.progress) statusEl.textContent += "（" + task.progress + "）";
          }
        })
        .catch(function (err) {
          statusEl.textContent = "查询任务失败：" + err.message;
          statusEl.className = "status err";
          clearInterval(pollTimer); pollTimer = null;
          setBusy(indexStatus, false, indexButton);
        });
    }, 1500);
  }
})();
</script>
</body>
</html>
"""


def web_app_html() -> str:
    return _TEMPLATE.replace("__PRODUCT_NAME__", PRODUCT_NAME)
