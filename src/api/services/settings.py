"""Settings view and safe runtime configuration updates.

Exposes configuration state to the web client without ever leaking
secrets: API keys, tokens and passwords are reduced to a yes/no flag.
"""

import json
import os
import re
import tempfile
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
        "mcp_enabled": config.MCP_ENABLED,
        "mcp_servers": list_mcp_servers(),
        # Access protection (LAN token; loopback is always exempt)
        "lan_protection": bool((config.LAN_TOKEN or "").strip()),
    }


def list_mcp_servers() -> list[dict]:
    """Return a secret-free summary of configured external MCP servers."""
    from src.agent.mcp_client import parse_mcp_config

    servers = parse_mcp_config(config.MCP_CONFIG_PATH)
    result = []
    for name, value in sorted(servers.items()):
        if not isinstance(value, dict):
            continue
        server_type = str(value.get("type") or "local").lower()
        if server_type == "remote":
            target = _mask_base_url(str(value.get("url") or ""))
        else:
            command = value.get("command") or []
            target = str(command[0]) if isinstance(command, list) and command else ""
        result.append({
            "name": str(name),
            "type": server_type,
            "enabled": bool(value.get("enabled", True)),
            "target": target,
        })
    return result


def _drop_agent_for_mcp_reload() -> None:
    from src.resources import ResourceManager

    manager = ResourceManager.get_instance()
    manager.clear_agent_cache()
    registry = getattr(manager, "tool_registry", None)
    if registry is not None:
        registry.unregister_plugin("mcp")
        registry._mcp_catalog_discovered = False


def set_mcp_enabled(enabled: bool) -> dict:
    """Persist the global external-MCP switch and reload the Agent lazily."""
    from dotenv import set_key

    value = "true" if enabled else "false"
    dotenv_path = Path(config.KNOWLEDGE_HOME) / ".env"
    dotenv_path.parent.mkdir(parents=True, exist_ok=True)
    dotenv_path.touch(exist_ok=True)
    set_key(str(dotenv_path), "MCP_ENABLED", value)
    os.environ["MCP_ENABLED"] = value
    config.MCP_ENABLED = enabled
    _drop_agent_for_mcp_reload()
    return {"ok": True, "mcp_enabled": enabled, "servers": list_mcp_servers()}


def set_mcp_server_enabled(name: str, enabled: bool) -> dict:
    """Toggle one existing server in mcp.json and reload the Agent lazily."""
    path = Path(config.MCP_CONFIG_PATH)
    if not path.is_file():
        raise ValueError("MCP 配置文件不存在")
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError("MCP 配置文件无法读取或不是有效 JSON") from exc
    if not isinstance(document, dict):
        raise ValueError("MCP 配置必须是 JSON 对象")
    servers = document.get("mcp", document)
    if not isinstance(servers, dict) or name not in servers or not isinstance(servers[name], dict):
        raise ValueError(f"MCP Server 不存在：{name}")
    servers[name]["enabled"] = enabled

    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(document, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)

    _drop_agent_for_mcp_reload()
    return {"ok": True, "name": name, "enabled": enabled, "servers": list_mcp_servers()}


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
    # Bump the answer-cache generation so an in-flight response from the old
    # model can never become a hit for the new model configuration.
    rm.invalidate_answer_cache()
    rm.clear_agent_cache()
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
