GRADING_PROMPT = (
    "你是一个文档相关性评估员。你的任务是从检索到的文档片段中判断其是否与用户问题相关。\n"
    "只需回答 '相关' 或 '不相关'，不要输出其他内容。\n"
    "问题: {question}\n"
    "文档片段: {document}\n"
    "评估结果:"
)


def grade_document(question: str, document: str, llm) -> bool:
    try:
        prompt = GRADING_PROMPT.format(question=question, document=document[:1000])
        response = llm.invoke(prompt)
        result = response.content.strip().replace(" ", "")
        # Match the complete verdict; "不相关" also contains "相关".
        return result.startswith("相关") and not result.startswith("不相关")
    except Exception:
        return True
