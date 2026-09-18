"""Settings view and safe runtime configuration updates.

Exposes configuration state to the web client without ever leaking
secrets: API keys, tokens and passwords are reduced to a yes/no flag.
"""

import os
import re
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import config


def list_provider_models(provider: str, base_url: str, api_key: str | None = None) -> list[str]:
    """Read the model ids advertised by an OpenAI-compatible provider."""
    import httpx

    provider = provider.strip().lower()
    base_url = base_url.strip().rstrip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", provider):
        raise ValueError("provider must use 1-32 lowercase letters, digits, '-' or '_'")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError("an http(s) base URL is required")
    key = (api_key or config.LLM_API_KEY or config.DEEPSEEK_API_KEY or "").strip()
    headers = {"Authorization": f"Bearer {key}"} if key else {}
    if provider == "ollama":
        headers.pop("Authorization", None)
    try:
        # Provider traffic is direct; this endpoint is explicitly used when
        # the user said the configured service does not require a proxy.
        response = httpx.get(f"{base_url}/models", headers=headers, timeout=10.0, trust_env=False)
        response.raise_for_status()
        payload = response.json()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 401:
            raise ValueError(
                "供应商拒绝了 API Key（401）。请填写当前模型供应商的 LLM API Key，"
                "不要填写飞书 App ID、App Secret 或机器人凭证。"
            ) from exc
        raise ValueError(f"读取供应商模型失败：HTTP {exc.response.status_code}") from exc
    except httpx.HTTPError as exc:
        raise ValueError(f"读取供应商模型失败：{exc}") from exc
    except ValueError as exc:
        raise ValueError("供应商返回的模型列表不是有效 JSON") from exc
    data = payload.get("data", []) if isinstance(payload, dict) else []
    models = sorted({str(item.get("id", "")).strip() for item in data if isinstance(item, dict) and item.get("id")})
    if not models:
        raise ValueError("供应商未返回可用模型")
    return models[:200]


def _mask_base_url(url: str) -> str:
    """Redact any credentials embedded in a base URL.

    Strips ``user:pass@`` from the authority and drops query parameters
    whose name looks like a key/token/secret."""
    try:
        parts = urlsplit(url)
        netloc = parts.netloc.rsplit("@", 1)[-1] if "@" in parts.netloc else parts.netloc
        query = parts.query
        if query:
            kept = []
            for pair in query.split("&"):
                name = pair.split("=", 1)[0].lower()
                if any(k in name for k in ("key", "token", "secret")):
                    continue
                kept.append(pair)
            query = "&".join(kept)
        return urlunsplit((parts.scheme, netloc, parts.path, query, parts.fragment))
    except Exception:
        return url


def get_settings_view() -> dict:
    """Safe, read-only snapshot of the configuration at process start."""
    return {
        # Data & paths
        "knowledge_home": str(config.KNOWLEDGE_HOME),
        "data_dir": str(config.DATA_DIR),
        "external_dir": str(config.EXTERNAL_DIR),
        "chroma_persist_dir": str(config.CHROMA_PERSIST_DIR),
        "chroma_ok": Path(config.CHROMA_PERSIST_DIR).is_dir(),
        "graph_persist_dir": str(config.GRAPH_PERSIST_DIR),
        # Embedding
        "embedding_model": config.EMBEDDING_MODEL,
        "embedding_device": config.EMBEDDING_DEVICE,
        # LLM
        "llm_model": config.LLM_MODEL,
        "llm_provider": config.LLM_PROVIDER,
        "llm_api_base": _mask_base_url(config.LLM_API_BASE or config.DEEPSEEK_API_BASE),
        "llm_api_configured": bool((config.LLM_API_KEY or config.DEEPSEEK_API_KEY or "").strip()),
        "rerank_llm": config.RERANK_LLM,
        "local_llm_base": _mask_base_url(config.LOCAL_LLM_BASE),
        "local_llm_model": config.LOCAL_LLM_MODEL,
        # Network / model sourcing
        "hf_endpoint": config.HF_ENDPOINT,
        "hf_offline": os.getenv("HF_HUB_OFFLINE", "").lower() in {"1", "true"},
        # Feature toggles
        "graph_enabled": config.ENABLE_GRAPH,
        "graph_llm_extraction": config.ENABLE_GRAPH_LLM_EXTRACTION,
        "hybrid_search": config.ENABLE_HYBRID_SEARCH,
        "grading": config.ENABLE_GRADING,
        "rewrite": config.ENABLE_REWRITE,
        "context_compression": config.ENABLE_CONTEXT_COMPRESSION,
        "chunk_size": config.CHUNK_SIZE,
        "chunk_overlap": config.CHUNK_OVERLAP,
        "top_k": config.TOP_K,
        "max_context_tokens": config.MAX_CONTEXT_TOKENS,
        # MCP
        "mcp_config_path": config.MCP_CONFIG_PATH,
        "mcp_enabled": Path(config.MCP_CONFIG_PATH).is_file(),
        # Access protection (LAN token; loopback is always exempt)
        "lan_protection": bool((config.LAN_TOKEN or "").strip()),
    }


def set_llm_config(provider: str, model: str, base_url: str, api_key: str | None) -> dict:
    """Persist and hot-apply an OpenAI-compatible LLM configuration."""
    from dotenv import set_key
    from src.llm.client import get_llm
    from src.resources import ResourceManager

    provider = provider.strip().lower()
    model = model.strip()
    base_url = base_url.strip().rstrip("/")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,31}", provider):
        raise ValueError("provider must use 1-32 lowercase letters, digits, '-' or '_'")
    if not model or not base_url.startswith(("http://", "https://")):
        raise ValueError("model and an http(s) base URL are required")

    dotenv_path = Path(config.KNOWLEDGE_HOME) / ".env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.touch(exist_ok=True)
    for key, value in {
        "LLM_PROVIDER": provider,
        "LLM_MODEL": model,
        "LLM_API_BASE": base_url,
    }.items():
        set_key(str(dotenv_path), key, value)
    if api_key is not None and api_key.strip():
        set_key(str(dotenv_path), "LLM_API_KEY", api_key.strip())

    config.LLM_PROVIDER = provider
    config.LLM_MODEL = model
    config.LLM_API_BASE = base_url
    if api_key is not None and api_key.strip():
        config.LLM_API_KEY = api_key.strip()

    # Drop the cached client and agent so the next request uses the new API.
    get_llm.cache_clear()
    rm = ResourceManager.get_instance()
    with rm._agent_lock:
        if rm.agent is not None:
            try:
                from src.agent.rag_agent import close_agent_checkpoint
                close_agent_checkpoint(rm.agent)
            except Exception:
                pass
        rm.agent = None
        rm.llm = None
    return {"ok": True, "provider": provider, "model": model, "requires_restart": False}


def set_graph_extraction_mode(enabled: bool) -> dict:
    """Persist the graph extraction mode (jieba / LLM) to .env.

    Mirrors the console ``/mode llm|jieba`` command: writes
    ``ENABLE_GRAPH_LLM_EXTRACTION`` and updates the in-process config so the
    change takes effect for the next index run without a restart.
    """
    from dotenv import set_key

    value = "true" if enabled else "false"
    dotenv_path = Path(config.KNOWLEDGE_HOME) / ".env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.touch(exist_ok=True)
    set_key(str(dotenv_path), "ENABLE_GRAPH_LLM_EXTRACTION", value)
    os.environ["ENABLE_GRAPH_LLM_EXTRACTION"] = value
    config.ENABLE_GRAPH_LLM_EXTRACTION = enabled
    return {"ok": True, "graph_llm_extraction": enabled}
