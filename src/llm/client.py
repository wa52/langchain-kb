from functools import lru_cache

from langchain_openai import ChatOpenAI

import config


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
