"""First-run DeepSeek API key bootstrap for the knowledge CLI."""

import os
import sys

from config import KNOWLEDGE_HOME


def _current_key() -> str:
    """Read the current key, preferring the live config value."""
    import config
    return getattr(config, "DEEPSEEK_API_KEY", "") or os.environ.get("DEEPSEEK_API_KEY", "")


def _is_tty() -> bool:
    return hasattr(sys.stdin, "isatty") and sys.stdin.isatty()


def _env_file() -> str:
    return str(KNOWLEDGE_HOME / ".env")


def _save_key_to_env(key: str) -> None:
    from dotenv import set_key
    env_path = _env_file()
    try:
        set_key(env_path, "DEEPSEEK_API_KEY", key)
    except Exception:
        # Fall back to appending if dotenv cannot rewrite the file.
        with open(env_path, "a", encoding="utf-8") as f:
            f.write(f"\nDEEPSEEK_API_KEY={key}\n")
    os.environ["DEEPSEEK_API_KEY"] = key
    import config
    config.DEEPSEEK_API_KEY = key


def _prompt_for_key() -> str | None:
    try:
        key = input("未检测到 DeepSeek API Key，请输入（可直接粘贴，用于本次及后续运行）: ")
    except (EOFError, KeyboardInterrupt):
        return None
    key = key.strip()
    if not key:
        return None
    if not key.startswith("sk-"):
        print("  [提示] Key 似乎不是以 sk- 开头，仍将保存。请确认输入正确。", file=sys.stderr)
    return key


def ensure_api_key() -> bool:
    """Ensure a DeepSeek API key is available.

    Returns True if a key is available after the call (existing or entered).
    Non-interactive environments (scripts, tests) skip the prompt.
    """
    if _current_key():
        return True
    if os.environ.get("KNOWLEDGE_SKIP_API_PROMPT", "").lower() in ("1", "true", "yes"):
        return False
    if not _is_tty():
        return False
    key = _prompt_for_key()
    if not key:
        print("  [错误] 未提供 API Key，无法使用 LLM 相关功能。", file=sys.stderr)
        return False
    _save_key_to_env(key)
    return True
