from functools import lru_cache

from langchain_openai import ChatOpenAI

from config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, LLM_MODEL, LOCAL_LLM_BASE, LOCAL_LLM_MODEL


@lru_cache(maxsize=2)
def get_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=temperature,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
    )


@lru_cache(maxsize=2)
def get_local_llm(temperature: float = 0) -> ChatOpenAI:
    """Ollama 本地模型（OpenAI 兼容端点），用于评分/压缩等轻量任务。"""
    return ChatOpenAI(
        model=LOCAL_LLM_MODEL,
        temperature=temperature,
        api_key="ollama",
        base_url=LOCAL_LLM_BASE,
        extra_body={"think": False},
    )
