from unittest.mock import MagicMock

from src.agent.chat_history import compress_history


def _make_turns(n: int):
    msgs = []
    for i in range(1, n + 1):
        msgs.append({"role": "user", "content": f"问题{i}"})
        msgs.append({"role": "assistant", "content": f"回答{i}"})
    return msgs


MOCK_LLM = MagicMock()
MOCK_LLM.invoke = MagicMock(return_value=MagicMock(content="用户提出了关于RAG和Agent的问题"))


class TestCompressHistory:

    def test_under_threshold_no_change(self):
        msgs = _make_turns(8)
        result = compress_history(msgs, MOCK_LLM, keep_rounds=10)
        assert result == msgs
        assert len(result) == 16

    def test_exact_threshold_no_change(self):
        msgs = _make_turns(10)
        result = compress_history(msgs, MOCK_LLM, keep_rounds=10)
        assert result == msgs
        assert len(result) == 20

    def test_compress_old_turns(self):
        msgs = _make_turns(12)
        result = compress_history(msgs, MOCK_LLM, keep_rounds=10)
        assert result[0]["role"] == "system"
        assert "摘要" in result[0]["content"]
        assert result[0]["content"].startswith("[历史摘要]")
        assert len(result) == 21  # 1 summary + 10*2 recent

    def test_last_ten_preserved(self):
        msgs = _make_turns(12)
        result = compress_history(msgs, MOCK_LLM, keep_rounds=10)
        recent = result[1:]
        assert recent[0] == {"role": "user", "content": "问题3"}
        assert recent[-1] == {"role": "assistant", "content": "回答12"}

    def test_empty_list(self):
        result = compress_history([], MOCK_LLM)
        assert result == []

    def test_llm_called_with_old_part(self):
        msgs = _make_turns(15)
        compress_history(msgs, MOCK_LLM, keep_rounds=10)
        call_arg = MOCK_LLM.invoke.call_args[0][0]
        assert "问题1" in call_arg or "问题2" in call_arg
        MOCK_LLM.invoke.reset_mock()

    def test_single_turn_no_compress(self):
        msgs = _make_turns(1)
        result = compress_history(msgs, MOCK_LLM, keep_rounds=10)
        assert result == msgs
