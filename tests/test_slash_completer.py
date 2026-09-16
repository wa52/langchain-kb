from unittest.mock import patch

from prompt_toolkit.document import Document
from prompt_toolkit.completion import Completion

import src.cli.console as console_mod
from src.cli.console import SlashCompleter, _get_user_input


completer = SlashCompleter()


def _completions(text: str) -> list[Completion]:
    doc = Document(text=text, cursor_position=len(text))
    return list(completer.get_completions(doc, None))


class TestSlashCompleter:

    def test_slash_shows_all(self):
        result = _completions("/")
        assert len(result) == 15
        assert all(c.text.startswith("/") for c in result)

    def test_slash_a_filters(self):
        result = _completions("/a")
        assert len(result) == 1
        assert result[0].text == "/add"

    def test_slash_h_filters(self):
        result = _completions("/h")
        assert len(result) == 1
        assert result[0].text == "/help"

    def test_plain_text_no_completions(self):
        result = _completions("hello")
        assert len(result) == 0

    def test_partial_slash_re(self):
        result = _completions("/re")
        assert all("/re" in c.text for c in result)

    def test_exact_slash_mode(self):
        result = _completions("/mode")
        assert result[0].text == "/mode"


class TestGracefulFallback:

    def test_module_has_flag(self):
        assert isinstance(console_mod._HAS_PROMPT_TOOLKIT, bool)

    def test_slash_completer_class_exists(self):
        assert hasattr(console_mod, "SlashCompleter")

    def test_uses_input_when_pt_unavailable(self):
        with patch.object(console_mod, "_HAS_PROMPT_TOOLKIT", False):
            with patch("builtins.input", return_value="test") as mock_input:
                result = _get_user_input("> ")
                assert result == "test"
                mock_input.assert_called_once_with("> ")

    def test_uses_pt_when_available(self):
        with patch.object(console_mod, "_HAS_PROMPT_TOOLKIT", True):
            with patch.object(console_mod, "pt_prompt", return_value="test") as mock_pt:
                result = _get_user_input("> ")
                assert result == "test"
                mock_pt.assert_called_once()
                args, kwargs = mock_pt.call_args
                assert args[0] == "> "
                assert isinstance(kwargs["completer"], console_mod.SlashCompleter)
