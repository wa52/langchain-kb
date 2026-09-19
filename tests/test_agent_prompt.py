from src.agent.prompt import build_agent_prompt


def test_prompt_configures_tool_loop_and_avoids_repeated_rag_scans():
    prompt = build_agent_prompt(["browser_search"])

    assert "write_todos" in prompt
    assert "观察结果" in prompt
    assert "最多再检索两次" in prompt
    assert "避免重复调用同一工具" in prompt
    assert "Few-shot" in prompt
    assert "browser_search" in prompt


def test_prompt_does_not_claim_unavailable_external_tools():
    prompt = build_agent_prompt()
    assert "无外部 MCP" in prompt
    assert "不要声称可以联网" in prompt


def test_prompt_requires_source_scoped_technical_claims():
    prompt = build_agent_prompt()

    assert "示例代码只能证明" in prompt
    assert "不得从算子名、变量名或参数位置推断" in prompt
    assert "不要罗列未支撑结论的来源" in prompt
