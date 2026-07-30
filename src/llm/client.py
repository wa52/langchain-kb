from functools import lru_cache

from langchain_openai import ChatOpenAI

from config import DEEPSEEK_API_BASE, DEEPSEEK_API_KEY, LLM_MODEL


@lru_cache(maxsize=2)
def get_llm(temperature: float = 0) -> ChatOpenAI:
    return ChatOpenAI(
        model=LLM_MODEL,
        temperature=temperature,
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
    )
