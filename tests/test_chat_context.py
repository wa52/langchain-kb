from unittest.mock import MagicMock, patch

import pytest

from src.api.services import chat as chat_mod


def _history(n: int) -> list[dict]:
    msgs = []
    for i in range(n):
        msgs.append({"role": "user", "content": f"问题{i}"})
        msgs.append({"role": "assistant", "content": f"回答{i}"})
    msgs.append({"role": "user", "content": "当前问题"})
    return msgs


class TestContextCompression:
    @pytest.fixture(autouse=True)
    def _tight_budget(self):
        with (
            patch.object(chat_mod, "HISTORY_COMPRESS_ROUNDS", 2),
            patch.object(chat_mod, "HISTORY_MAX_TOKENS", 10**9),
        ):
            yield

    def test_short_history_unchanged(self):
        msgs = _history(2)
        assert chat_mod._maybe_compress_history(msgs) == msgs

    def test_long_history_compresses_with_llm(self):
        msgs = _history(5)
        rm = MagicMock()
        rm.is_ready.return_value = True
        rm.llm = MagicMock()
        rm.llm.invoke.return_value = MagicMock(content="历史摘要")
        with patch("src.resources.ResourceManager.get_instance", return_value=rm):
            out = chat_mod._maybe_compress_history(msgs)
        assert out[-1] == msgs[-1], "当前问题不应被压缩"
        assert out[0]["role"] == "system"
        assert "历史摘要" in out[0]["content"]
        assert len([m for m in out if m["role"] == "user"]) <= 3

    def test_long_history_without_llm_still_compresses(self):
        msgs = _history(5)
        rm = MagicMock()
        rm.is_ready.return_value = False
        with patch("src.resources.ResourceManager.get_instance", return_value=rm):
            out = chat_mod._maybe_compress_history(msgs)
        assert out[-1] == msgs[-1]
        assert out[0]["role"] == "system"
        assert "[历史摘要]" in out[0]["content"]

    def test_token_budget_trims_oldest_messages(self):
        with patch.object(chat_mod, "HISTORY_COMPRESS_ROUNDS", 10**9), patch.object(chat_mod, "HISTORY_MAX_TOKENS", 1):
            msgs = _history(4)
            out = chat_mod._maybe_compress_history(msgs)
            assert len(out) < len(msgs), "超出 token 预算应截断最早消息"
            assert out[-1] == msgs[-1], "当前问题应保留"
            assert out[0]["role"] == "user"

    def test_estimated_tokens(self):
        assert chat_mod._estimated_tokens("中文汉字") == 4
        assert chat_mod._estimated_tokens("abcd") == 1
