from functools import lru_cache

import httpx
from langchain_openai import ChatOpenAI

import config


_REQUEST_TIMEOUT_SECONDS = 90.0
_STREAM_CHUNK_TIMEOUT_SECONDS = 45.0


def _provider_runtime_options() -> dict:
    """Return safe model options for the configured OpenAI-compatible API."""
    options: dict = {
        "timeout": _REQUEST_TIMEOUT_SECONDS,
        "stream_chunk_timeout": _STREAM_CHUNK_TIMEOUT_SECONDS,
    }
    # GLM-5.3 always reasons. Its default is the most expensive/slowest tier,
    # which can leave a tool-using turn with no visible output for a long time.
    # The provider accepts only low/high/max; low keeps ordinary KB and code
    # requests responsive while preserving native tool calling.
    if (
        config.LLM_PROVIDER == "zhipu"
        and config.LLM_MODEL.strip().lower().startswith("glm-5.3")
    ):
        options["reasoning_effort"] = "low"
        # GLM's non-streaming tool-call endpoint is reliable, while its
        # streamed tool-call path can withhold every event for a full Agent
        # turn. LangChain still streams ordinary answer tokens after tools.
        options["disable_streaming"] = "tool_calling"
    return options


def _direct_http_options() -> dict:
    """Keep provider traffic independent from machine-wide proxy settings."""
    timeout = httpx.Timeout(_REQUEST_TIMEOUT_SECONDS)
    return {
        "http_client": httpx.Client(timeout=timeout, trust_env=False),
        "http_async_client": httpx.AsyncClient(timeout=timeout, trust_env=False),
    }


@lru_cache(maxsize=2)
def get_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=config.LLM_MODEL,
        temperature=temperature,
        api_key=(
            config.LLM_API_KEY
            or ("ollama" if config.LLM_PROVIDER == "ollama" else config.DEEPSEEK_API_KEY)
        ),
        base_url=config.LLM_API_BASE or config.DEEPSEEK_API_BASE,
        **_provider_runtime_options(),
        **_direct_http_options(),
    )


@lru_cache(maxsize=2)
def get_local_llm(temperature: float = 0) -> ChatOpenAI:
    """Ollama 本地模型（OpenAI 兼容端点），用于评分/压缩等轻量任务。"""
    return ChatOpenAI(
        model=config.LOCAL_LLM_MODEL,
        temperature=temperature,
        api_key="ollama",
        base_url=config.LOCAL_LLM_BASE,
        extra_body={"think": False},
    )
