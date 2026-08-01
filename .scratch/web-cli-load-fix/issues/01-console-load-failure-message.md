# 01 — Console reports agent-load failure instead of infinite "loading"

**What to build:** When the background embedding/agent load fails, `knowledge cli` must stop telling the user "知识库正在加载中" and surface a clear load-failed message — on both typed prompts and bare Enter — while staying operable for non-agent commands (`/help`, `/config`, `/exit`). Today, after a load failure, the main loop's plain-text fallback funnels both "not ready" and "failed" through `_sync_agent_state`, which returns False for both, so the console prints "正在加载中" forever; empty input returns "" early and hits that same misleading branch.

**Blocked by:** None — can start immediately

**Status:** ready-for-agent

- [ ] `src/cli/console.py` main loop distinguishes `_agent_result is an Exception` from still-loading; failed → echo `[错误] 知识库加载失败…` (reuse existing failure copy); bare Enter no longer loops "正在加载中"
- [ ] `tests/test_console.py` adds a `TestLoadingState`-style case: after load failure, plain input and empty input both yield the failure message (not "正在加载中"), and `/help` still works
- [ ] `python -m pytest tests/test_console.py -v` green
- [ ] Manual: force a load failure (e.g., `HF_HUB_OFFLINE=1` with empty cache, or bad endpoint); `knowledge cli` shows the failure message and `/exit` exits cleanly