REWRITE_PROMPT = (
    "根据用户的问题，分析其背后的语义意图，生成一个更清晰、更适合检索的改进问题。\n"
    "原始问题: {question}\n"
    "改进问题:"
)


def rewrite_question(question: str, llm) -> str:
    prompt = REWRITE_PROMPT.format(question=question)
    response = llm.invoke(prompt)
    return response.content.strip()
