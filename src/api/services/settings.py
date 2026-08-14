"""Read-only settings view.

Exposes configuration state to the web client without ever leaking
secrets: API keys, tokens and passwords are reduced to a yes/no flag.
"""

import os
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import config


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
        "llm_api_base": _mask_base_url(config.DEEPSEEK_API_BASE),
        "llm_api_configured": bool((config.DEEPSEEK_API_KEY or "").strip()),
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
        # Access protection (LAN token protection is not implemented yet)
        "lan_protection": False,
    }
