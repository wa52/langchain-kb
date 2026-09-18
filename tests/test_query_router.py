from src.agent.query_router import QueryRoute, route_query


def test_greeting_and_general_question_are_direct():
    assert route_query("你好") == QueryRoute.DIRECT
    assert route_query("Python 的列表推导式怎么写？") == QueryRoute.DIRECT


def test_text_rewrite_uses_direct_path():
    assert route_query("把这段话润色一下：交付已经完成") == QueryRoute.DIRECT


def test_knowledge_and_domain_questions_use_agent():
    assert route_query("知识库里有没有相机标定资料？") == QueryRoute.AGENT
    assert route_query("工业视觉划痕检测怎么优化？") == QueryRoute.AGENT
    assert route_query("查一下最新相机规格") == QueryRoute.AGENT


def test_short_follow_up_keeps_previous_agent_route():
    history = [
        {"role": "user", "content": "知识库里有什么？"},
        {"role": "assistant", "content": "有标定资料", "route": "agent"},
    ]
    assert route_query("具体呢？", history) == QueryRoute.AGENT


def test_short_follow_up_after_direct_answer_stays_direct():
    history = [
        {"role": "user", "content": "解释 Python 列表"},
        {"role": "assistant", "content": "列表是一种容器", "route": "direct"},
    ]
    assert route_query("举个例子", history) == QueryRoute.DIRECT
