"""Feishu (Lark) bot backed by the knowledge-base RAG API.

Runs as a standalone process using the official ``lark-oapi`` SDK in
long-connection (WebSocket) mode, so no public URL / ngrok is required.
Text messages are forwarded to ``POST /api/v1/chat``; the answer is sent
back in the same chat thread. Each Feishu user keeps their own
conversation history. Commands include ``/new``, ``/sessions``, ``/use <序号>``,
``/delete <序号>``, and ``/current``.

``lark_oapi`` is imported lazily so this module (and its message-handling
logic) stays importable without the SDK installed, e.g. under pytest.
"""

import json
import logging
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import httpx

from config import KNOWLEDGE_HOME  # noqa: F401  (loads .env on import)
from src.feishu.session_map import SessionStore

log = logging.getLogger("feishu-bot")

KB_API_BASE = os.getenv("KB_API_BASE", "http://127.0.0.1:8000")
CHAT_URL = f"{KB_API_BASE}/api/v1/chat"
CHAT_STREAM_URL = f"{KB_API_BASE}/api/v1/chat/stream"
RESET_WORDS = {"/new", "/新会话"}
HELP_WORDS = {"/help", "/帮助"}
FEISHU_MAX_CONCURRENCY = max(1, int(os.getenv("FEISHU_MAX_CONCURRENCY", "10")))
FEISHU_QUEUE_SIZE = max(0, int(os.getenv("FEISHU_QUEUE_SIZE", "50")))
FEISHU_DEDUPE_TTL = max(60.0, float(os.getenv("FEISHU_DEDUPE_TTL", "600")))


class _MessageDeduper:
    """Bounded, TTL-based event deduplication for Feishu retries."""

    def __init__(self, ttl: float = FEISHU_DEDUPE_TTL, max_entries: int = 10000):
        self.ttl = ttl
        self.max_entries = max_entries
        self._items: dict[str, float] = {}
        self._lock = threading.Lock()

    def seen(self, message_id: str) -> bool:
        now = time.monotonic()
        with self._lock:
            expired = [key for key, value in self._items.items() if now - value > self.ttl]
            for key in expired:
                self._items.pop(key, None)
            if message_id in self._items:
                return True
            self._items[message_id] = now
            while len(self._items) > self.max_entries:
                self._items.pop(next(iter(self._items)))
            return False


def _message_text(event) -> str | None:
    message = event.event.message
    if message is None or message.message_type != "text" or not message.content:
        return None
    try:
        return json.loads(message.content).get("text", "").strip()
    except Exception:
        return None


def _sender_key(event) -> str:
    sender = event.event.sender
    if sender is not None:
        sender_id = getattr(sender, "sender_id", None)
        open_id = getattr(sender_id, "open_id", None)
        if open_id:
            return open_id
    return event.event.message.chat_id


def _session_command(store: SessionStore, sender_key: str, text: str) -> str | None:
    """Handle Feishu-only conversation management commands."""
    command = text.strip()
    if command in HELP_WORDS:
        return "可用命令：\n/new 新建会话\n/sessions 查看会话\n/use <序号> 切换会话\n/delete <序号> 删除会话\n/clear-all 清空全部历史\n/current 查看当前会话"
    if command in {"/current", "/当前"}:
        return f"当前会话：{store.get(sender_key) or '无（下一条消息会自动新建）'}"
    session_ids = store.list(sender_key)
    if command in {"/sessions", "/会话"}:
        if not session_ids:
            return "暂无已保存会话。发送普通问题即可新建会话。"
        current = store.get(sender_key)
        lines = ["你的会话："]
        for index, session_id in enumerate(session_ids[:10], 1):
            marker = "*" if session_id == current else " "
            lines.append(f"{marker}{index}. {session_id}")
        return "\n".join(lines)
    if command in {"/clear-all", "/clear_all", "/清空"}:
        if not session_ids:
            return "没有可清空的历史会话。"
        try:
            from src.agent.chat_history import delete_history
            for session_id in session_ids:
                delete_history(session_id)
        except Exception:
            log.exception("failed to clear Feishu session history")
            return "清空历史失败，请稍后重试。"
        store.clear(sender_key)
        return (
            f"已清空 {len(session_ids)} 个知识库历史会话。\n"
            "飞书聊天窗口中已经发送的提问和回答消息不会被删除；如需清空窗口，请在飞书客户端删除或新建会话。"
        )
    parts = command.split(maxsplit=1)
    if len(parts) == 2 and parts[0] in {"/use", "/切换"}:
        target = _resolve_session_target(session_ids, parts[1])
        if target and store.switch(sender_key, target):
            return f"已切换到会话：{target}"
        return "找不到这个会话。请先发送 /sessions 查看序号。"
    if len(parts) == 2 and parts[0] in {"/delete", "/删除"}:
        target = _resolve_session_target(session_ids, parts[1])
        if not target or not store.remove(sender_key, target):
            return "找不到这个会话。请先发送 /sessions 查看序号。"
        try:
            from src.agent.chat_history import delete_history
            delete_history(target)
        except Exception:
            log.exception("failed to delete Feishu session history: %s", target)
        return f"已删除会话：{target}"
    return None


def _resolve_session_target(session_ids: list[str], value: str) -> str | None:
    value = value.strip()
    if value.isdigit():
        index = int(value) - 1
        return session_ids[index] if 0 <= index < len(session_ids) else None
    return value if value in session_ids else None


def ask_knowledge_base(query: str, session_id: str | None) -> tuple[str, str | None]:
    """Call the knowledge-base chat API; return (answer, new_session_id)."""
    payload: dict = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    with httpx.Client(timeout=120.0) as client:
        resp = client.post(CHAT_URL, json=payload)
        resp.raise_for_status()
        data = resp.json()
    return str(data.get("answer", "")), data.get("conversation_id")


def stream_knowledge_base(query: str, session_id: str | None):
    """Yield ``(event_type, data)`` pairs from the knowledge-base SSE API."""
    payload: dict = {"query": query}
    if session_id:
        payload["session_id"] = session_id
    with httpx.Client(timeout=120.0) as client:
        with client.stream("POST", CHAT_STREAM_URL, json=payload) as response:
            response.raise_for_status()
            event_type = None
            event_data: list[str] = []
            for line in response.iter_lines():
                if line.startswith("event:"):
                    event_type = line[6:].strip()
                elif line.startswith("data:"):
                    event_data.append(line[5:].lstrip())
                elif not line and event_type:
                    try:
                        data = json.loads("".join(event_data)) if event_data else {}
                    except json.JSONDecodeError:
                        data = {}
                    yield event_type, data
                    event_type = None
                    event_data = []


def process_incoming_message(
    store: SessionStore,
    reply_fn,
    message_id: str,
    chat_id: str,
    chat_type: str,
    text: str | None,
    sender_key: str,
    ask_fn=ask_knowledge_base,
) -> None:
    """Handle one Feishu message: reset session, call KB, or send a hint.

    ``reply_fn(message_id, chat_id, chat_type, text)`` is the transport-
    independent reply hook, so tests can inject a spy.
    """
    if not text:
        reply_fn(message_id, chat_id, chat_type, "目前仅支持文本消息，请直接发送文字提问。")
        return
    command_reply = _session_command(store, sender_key, text)
    if command_reply is not None:
        reply_fn(message_id, chat_id, chat_type, command_reply)
        return
    if text in RESET_WORDS:
        store.clear(sender_key)
        reply_fn(message_id, chat_id, chat_type, "已开启新会话，你可以开始提问了。")
        return
    session_id = store.get(sender_key)
    try:
        answer, new_session_id = ask_fn(text, session_id)
    except Exception:
        log.exception("knowledge base call failed")
        reply_fn(message_id, chat_id, chat_type, "知识库暂时不可用，请稍后再试。")
        return
    if new_session_id:
        store.set(sender_key, new_session_id)
    if not answer:
        reply_fn(message_id, chat_id, chat_type, "没有找到相关内容，换个问法试试？")
        return
    reply_fn(message_id, chat_id, chat_type, answer)


def process_incoming_stream(
    store: SessionStore,
    stream_reply_fn,
    message_id: str,
    chat_id: str,
    chat_type: str,
    text: str | None,
    sender_key: str,
) -> None:
    """Handle a message with incremental Feishu message updates."""
    if not text:
        stream_reply_fn(message_id, chat_id, chat_type, "目前仅支持文本消息，请直接发送文字提问。", None)
        return
    command_reply = _session_command(store, sender_key, text)
    if command_reply is not None:
        stream_reply_fn(message_id, chat_id, chat_type, command_reply, None)
        return
    if text in RESET_WORDS:
        store.clear(sender_key)
        stream_reply_fn(message_id, chat_id, chat_type, "已开启新会话，你可以开始提问了。", None)
        return
    try:
        new_session_id = stream_reply_fn(
            message_id, chat_id, chat_type, text, store.get(sender_key)
        )
    except Exception:
        log.exception("streaming knowledge base call failed")
        stream_reply_fn(message_id, chat_id, chat_type, "知识库暂时不可用，请稍后再试。", None)
        return
    if new_session_id:
        store.set(sender_key, new_session_id)


class FeishuBot:
    def __init__(self, app_id: str, app_secret: str, store: SessionStore | None = None):
        import lark_oapi as lark

        self.store = store or SessionStore()
        self.client = lark.Client.builder().app_id(app_id).app_secret(app_secret).build()
        self._executor = ThreadPoolExecutor(
            max_workers=FEISHU_MAX_CONCURRENCY,
            thread_name_prefix="feishu-chat",
        )
        self._capacity = threading.BoundedSemaphore(
            FEISHU_MAX_CONCURRENCY + FEISHU_QUEUE_SIZE
        )
        self._deduper = _MessageDeduper()
        self._sender_locks: dict[str, threading.Lock] = {}
        self._sender_locks_guard = threading.Lock()
        handler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._on_message)
            .build()
        )
        self.ws_client = lark.ws.Client(
            app_id,
            app_secret,
            event_handler=handler,
            log_level=lark.LogLevel.INFO,
        )

    def _on_message(self, event) -> None:
        message = event.event.message
        if message is None:
            return
        text = _message_text(event)
        log.info(
            "received message id=%s chat_type=%s msg_type=%s text=%r sender=%s",
            message.message_id,
            message.chat_type,
            message.message_type,
            text,
            _sender_key(event),
        )
        message_id = message.message_id or f"{message.chat_id}:{time.monotonic_ns()}"
        sender_key = _sender_key(event)
        if self._deduper.seen(message_id):
            log.info("ignoring duplicate Feishu event message_id=%s", message_id)
            return
        if not self._capacity.acquire(blocking=False):
            self._reply(
                message_id,
                message.chat_id,
                message.chat_type,
                "当前请求较多，请稍后再试。",
            )
            return
        try:
            self._executor.submit(
                self._run_message,
                message_id,
                message.chat_id,
                message.chat_type,
                text,
                sender_key,
            )
        except RuntimeError:
            self._capacity.release()
            self._reply(message_id, message.chat_id, message.chat_type, "服务正在关闭，请稍后再试。")

    def _run_message(
        self,
        message_id: str,
        chat_id: str,
        chat_type: str,
        text: str | None,
        sender_key: str,
    ) -> None:
        with self._sender_locks_guard:
            sender_lock = self._sender_locks.setdefault(sender_key, threading.Lock())
        try:
            with sender_lock:
                process_incoming_stream(
                    self.store,
                    self._stream_reply,
                    message_id,
                    chat_id,
                    chat_type,
                    text,
                    sender_key,
                )
        finally:
            self._capacity.release()

    def _on_p2p_chat_entered(self, event) -> None:
        """Intentionally do nothing; the bot only replies after a user message."""
        return

    def _reply(self, message_id: str, chat_id: str, chat_type: str, text: str) -> None:
        import lark_oapi as lark
        from lark_oapi.api.im.v1 import (
            CreateMessageRequest,
            CreateMessageRequestBody,
            ReplyMessageRequest,
            ReplyMessageRequestBody,
        )

        content = json.dumps({"text": text}, ensure_ascii=False)
        try:
            if chat_type == "p2p":
                request = (
                    CreateMessageRequest.builder()
                    .receive_id_type("chat_id")
                    .request_body(
                        CreateMessageRequestBody.builder()
                        .receive_id(chat_id)
                        .msg_type("text")
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self.client.im.v1.message.create(request)
            else:
                request = (
                    ReplyMessageRequest.builder()
                    .message_id(message_id)
                    .request_body(
                        ReplyMessageRequestBody.builder()
                        .msg_type("text")
                        .content(content)
                        .build()
                    )
                    .build()
                )
                response = self.client.im.v1.message.reply(request)
            if not response.success():
                log.error(
                    "send failed code=%s msg=%s log_id=%s",
                    response.code,
                    response.msg,
                    response.get_log_id(),
                )
            else:
                log.info("reply sent message_id=%s", message_id)
                return getattr(getattr(response, "data", None), "message_id", None)
        except Exception:
            log.exception("failed to send reply")
        return None

    def _update_message(self, message_id: str, text: str) -> None:
        """Replace a previously sent placeholder with the latest answer."""
        import lark_oapi.api.im.v1 as im

        content = json.dumps({"text": text or "正在思考…"}, ensure_ascii=False)
        request = (
            im.UpdateMessageRequest.builder()
            .message_id(message_id)
            .request_body(
                im.UpdateMessageRequestBody.builder()
                .msg_type("text")
                .content(content)
                .build()
            )
            .build()
        )
        response = self.client.im.v1.message.update(request)
        if not response.success():
            log.error(
                "stream update failed code=%s msg=%s log_id=%s",
                response.code,
                response.msg,
                response.get_log_id(),
            )

    def _stream_reply(
        self,
        message_id: str,
        chat_id: str,
        chat_type: str,
        query_or_text: str,
        session_id: str | None,
    ) -> str | None:
        """Send a placeholder, then update it as SSE tokens arrive."""
        if session_id is None and query_or_text in {
            "目前仅支持文本消息，请直接发送文字提问。",
            "已开启新会话，你可以开始提问了。",
            "知识库暂时不可用，请稍后再试。",
        }:
            self._reply(message_id, chat_id, chat_type, query_or_text)
            return None
        placeholder_id = self._reply(message_id, chat_id, chat_type, "正在思考…")
        if not placeholder_id:
            raise RuntimeError("无法发送飞书占位消息")
        parts: list[str] = []
        new_session_id = session_id
        last_update = 0.0
        for event_type, data in stream_knowledge_base(query_or_text, session_id):
            if event_type == "token":
                parts.append(str(data.get("text", "")))
                now = time.monotonic()
                if now - last_update >= 0.8:
                    self._update_message(placeholder_id, "".join(parts))
                    last_update = now
            elif event_type == "message_end":
                new_session_id = data.get("session_id") or new_session_id
            elif event_type == "error":
                raise RuntimeError(str(data.get("error", "知识库暂时不可用")))
        self._update_message(placeholder_id, "".join(parts) or "没有找到相关内容，换个问法试试？")
        return new_session_id

    def start(self) -> None:
        self.ws_client.start()

    def stop(self) -> None:
        """Release worker threads when the Feishu bridge is shutting down."""
        self._executor.shutdown(wait=False, cancel_futures=True)


def get_feishu_credentials() -> tuple[str, str]:
    """Read Feishu credentials, preferring the repo `.env` file.

    A user/machine-level `FEISHU_APP_ID` env var (e.g. a bridge assistant)
    would otherwise override `.env` because load_dotenv() does not overwrite
    existing variables. We read the file directly so the knowledge-base app
    in `.env` always wins.
    """
    from dotenv import dotenv_values

    from config import KNOWLEDGE_HOME

    values = dotenv_values(KNOWLEDGE_HOME / ".env")
    app_id = (values.get("FEISHU_APP_ID") or os.getenv("FEISHU_APP_ID") or "").strip()
    app_secret = (values.get("FEISHU_APP_SECRET") or os.getenv("FEISHU_APP_SECRET") or "").strip()
    return app_id, app_secret


def run_feishu_bot() -> None:
    app_id, app_secret = get_feishu_credentials()
    if not app_id or not app_secret:
        raise SystemExit("FEISHU_APP_ID / FEISHU_APP_SECRET 未配置（请写入 .env）")
    log.info("Feishu bot connecting via long connection (app_id=%s) ...", app_id)
    FeishuBot(app_id, app_secret).start()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run_feishu_bot()
