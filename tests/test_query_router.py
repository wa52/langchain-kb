from src.agent.query_router import QueryRoute, parse_route_command, route_query


def test_greeting_and_general_question_are_direct():
    assert route_query("你好") == QueryRoute.DIRECT
    assert route_query("Python 的列表推导式怎么写？") == QueryRoute.DIRECT


def test_text_rewrite_uses_direct_path():
    assert route_query("把这段话润色一下：交付已经完成") == QueryRoute.DIRECT


def test_knowledge_and_domain_questions_use_fast_rag():
    assert route_query("知识库里有没有相机标定资料？") == QueryRoute.FAST_RAG
    assert route_query("工业视觉划痕检测怎么优化？") == QueryRoute.FAST_RAG
    assert route_query("查一下最新相机规格") == QueryRoute.AGENT


def test_short_follow_up_keeps_previous_fast_rag_route():
    history = [
        {"role": "user", "content": "知识库里有什么？"},
        {"role": "assistant", "content": "有标定资料", "route": "fast_rag"},
    ]
    assert route_query("具体呢？", history) == QueryRoute.FAST_RAG


def test_short_follow_up_after_direct_answer_stays_direct():
    history = [
        {"role": "user", "content": "解释 Python 列表"},
        {"role": "assistant", "content": "列表是一种容器", "route": "direct"},
    ]
    assert route_query("举个例子", history) == QueryRoute.DIRECT


def test_force_route_commands_are_parsed_without_leaking_to_model():
    assert parse_route_command("/rag 相机标定") == (QueryRoute.FAST_RAG, "相机标定")
    assert parse_route_command("/ask 写一封邮件") == (QueryRoute.DIRECT, "写一封邮件")
    assert parse_route_command("/agent 查网页") == (QueryRoute.AGENT, "查网页")
