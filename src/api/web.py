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
    display: grid; grid-template-columns: 280px minmax(0, 1fr);
    gap: 16px;
    max-width: 1200px; margin: 0 auto; padding: 16px;
    height: calc(100vh - 110px);
  }
  @media (max-width: 760px) {
    .layout { grid-template-columns: 1fr; }
    .sessions-panel { display: none; }
  }
  .panel {
    background: var(--panel); border: 1px solid var(--border);
    border-radius: 12px; padding: 16px;
    display: flex; flex-direction: column;
    min-height: 0;
  }
  .sessions-panel { overflow: hidden; }
  .chat-panel { flex: 1; }
  .panel h2 { font-size: 15px; margin-bottom: 12px; }
  .row { display: flex; gap: 8px; }
  #chat-log {
    flex: 1; min-height: 0;
    overflow-y: auto;
    margin-top: 12px;
    padding-right: 4px;
  }
  #session-list {
    flex: 1; min-height: 0;
    overflow-y: auto;
    margin-top: 8px;
    list-style: none;
  }
  #session-list li {
    padding: 10px 12px;
    border-radius: 8px;
    cursor: pointer;
    margin-bottom: 4px;
    border: 1px solid transparent;
  }
  #session-list li:hover { background: var(--bg); }
  #session-list li.active {
    background: var(--bg);
    border-color: var(--primary);
  }
  #session-list .s-title {
    font-size: 14px; font-weight: 600;
    white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  #session-list .s-meta {
    font-size: 12px; color: var(--muted);
    margin-top: 2px;
  }
  #session-list .s-del {
    float: right;
    font-size: 12px;
    color: var(--danger);
    background: none; border: none;
    min-height: auto; padding: 0 4px;
    cursor: pointer;
    opacity: 0;
  }
  #session-list li:hover .s-del { opacity: 1; }
  .new-chat-btn {
    width: 100%; margin-top: 8px;
  }
  .empty-sessions { color: var(--muted); font-size: 13px; padding: 8px 4px; }
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
  .status { font-size: 14px; margin-top: 8px; }
  .status.err { color: var(--danger); }
  .status.ok { color: var(--ok); }
  .status.busy { color: var(--muted); }
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
    <section class="panel sessions-panel" id="sessions-view" aria-labelledby="sessions-title">
      <h2 id="sessions-title">历史会话</h2>
      <ul id="session-list" aria-live="polite"></ul>
      <button type="button" id="new-chat-btn" class="new-chat-btn">＋ 新建对话</button>
    </section>

    <section class="panel chat-panel" id="chat-view" aria-labelledby="chat-title">
      <h2 id="chat-title">问答</h2>
      <div class="out" id="chat-log" aria-live="polite" aria-busy="false"></div>
      <p class="hint" id="chat-hint">基于知识库检索增强生成，可连续追问。</p>
      <form id="chat-form" class="row">
        <input id="chat-input" type="text" placeholder="输入问题…" autocomplete="off" required aria-label="问题">
        <button type="submit">发送</button>
      </form>
    </section>
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

  async function getJSON(url) {
    var resp = await fetch(url, { headers: { "Accept": "application/json" } });
    var data = null;
    try { data = await resp.json(); } catch (e) { /* ignore */ }
    if (!resp.ok) {
      var detail = data && (data.detail || data.error);
      throw new Error(detail || ("请求失败 (" + resp.status + ")"));
    }
    return data;
  }

  // ---------- 会话列表 ----------
  var sessionList = document.getElementById("session-list");
  var newChatBtn = document.getElementById("new-chat-btn");
  var sessionsView = document.getElementById("sessions-view");
  var activeSessionId = null;

  function renderSessions(sessions) {
    sessionList.innerHTML = "";
    if (!sessions.length) {
      var li = document.createElement("li");
      li.className = "empty-sessions";
      li.textContent = "暂无历史会话";
      sessionList.appendChild(li);
      return;
    }
    sessions.forEach(function (s) {
      var li = document.createElement("li");
      li.dataset.id = s.id;
      if (s.id === activeSessionId) li.className = "active";
      var del = document.createElement("button");
      del.className = "s-del";
      del.textContent = "✕";
      del.title = "删除该会话";
      del.setAttribute("aria-label", "删除会话 " + s.title);
      del.addEventListener("click", function (e) {
        e.stopPropagation();
        deleteSession(s.id);
      });
      var title = document.createElement("div");
      title.className = "s-title";
      title.textContent = s.title || "空会话";
      var meta = document.createElement("div");
      meta.className = "s-meta";
      meta.textContent = (s.created || "") + " · " + s.turns + " 轮";
      li.appendChild(del);
      li.appendChild(title);
      li.appendChild(meta);
      li.addEventListener("click", function () { openSession(s.id); });
      sessionList.appendChild(li);
    });
  }

  function loadSessions() {
    return getJSON("/api/v1/sessions")
      .then(function (data) { renderSessions(data.sessions || []); })
      .catch(function (err) {
        sessionList.innerHTML = "";
        var li = document.createElement("li");
        li.className = "empty-sessions";
        li.textContent = "加载会话失败：" + err.message;
        sessionList.appendChild(li);
      });
  }

  function openSession(id) {
    getJSON("/api/v1/sessions/" + encodeURIComponent(id))
      .then(function (data) {
        activeSessionId = id;
        sessionId = id;
        chatHint.hidden = true;
        clearOutput(chatLog);
        var messages = data.messages || [];
        messages.forEach(function (m) {
          var role = m.role || m.type || "";
          var content = m.content || "";
          if (role === "user" || role === "human") {
            appendChat("user", escapeHtml(content));
          } else if (role === "assistant" || role === "ai") {
            appendChat("assistant", escapeHtml(content));
          } else if (role === "system") {
            appendChat("status", escapeHtml(content));
          }
        });
        markActiveSession();
        scrollChatToBottom(false);
      })
      .catch(function (err) {
        appendChat("err", "加载会话失败：" + escapeHtml(err.message));
      });
  }

  function newChat() {
    activeSessionId = null;
    sessionId = null;
    chatHint.hidden = false;
    clearOutput(chatLog);
    markActiveSession();
    chatInput.focus();
  }

  function deleteSession(id) {
    if (!window.confirm("确定删除该会话？")) return;
    fetch("/api/v1/sessions/" + encodeURIComponent(id), { method: "DELETE" })
      .then(function (resp) {
        if (!resp.ok && resp.status !== 204) throw new Error("删除失败 (" + resp.status + ")");
        if (activeSessionId === id) newChat();
        loadSessions();
      })
      .catch(function (err) {
        window.alert("删除失败：" + err.message);
      });
  }

  function markActiveSession() {
    var items = sessionList.querySelectorAll("li[data-id]");
    items.forEach(function (li) {
      li.classList.toggle("active", li.dataset.id === activeSessionId);
    });
  }

  newChatBtn.addEventListener("click", newChat);

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
        activeSessionId = sessionId;
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
        loadSessions();
      })
      .catch(function (err) {
        statusEl.remove();
        appendChat("err", "回答失败：" + escapeHtml(err.message));
      })
      .finally(function () { setBusy(chatLog, false, chatButton); });
  });

  function scrollChatToBottom(smooth) {
    chatLog.scrollTo({ top: chatLog.scrollHeight, behavior: smooth ? "smooth" : "auto" });
  }

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
    scrollChatToBottom(false);
    return body;
  }

  loadSessions();
})();
</script>
</body>
</html>
"""


def web_app_html() -> str:
    return _TEMPLATE.replace("__PRODUCT_NAME__", PRODUCT_NAME)
