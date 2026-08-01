from unittest.mock import patch

import pytest


class TestEnsureApiKey:
    def test_skips_when_key_already_set(self):
        import src.cli.api_key as api_key
        with patch.object(api_key, "_current_key", return_value="sk-existing"):
            assert api_key.ensure_api_key() is True

    def test_skips_in_non_tty_environment(self):
        import src.cli.api_key as api_key
        with (
            patch.object(api_key, "_current_key", return_value=""),
            patch.object(api_key, "_is_tty", return_value=False),
        ):
            assert api_key.ensure_api_key() is False

    def test_skips_when_env_skip_flag_set(self):
        import src.cli.api_key as api_key
        with (
            patch.object(api_key, "_current_key", return_value=""),
            patch.object(api_key, "_is_tty", return_value=True),
            patch.dict("os.environ", {"KNOWLEDGE_SKIP_API_PROMPT": "1"}, clear=False),
        ):
            assert api_key.ensure_api_key() is False

    def test_prompts_and_saves_key(self, tmp_path, monkeypatch):
        import src.cli.api_key as api_key
        env_file = tmp_path / ".env"
        monkeypatch.setattr(api_key, "KNOWLEDGE_HOME", tmp_path)
        with (
            patch.object(api_key, "_current_key", return_value=""),
            patch.object(api_key, "_is_tty", return_value=True),
            patch.object(api_key, "_prompt_for_key", return_value="sk-new-key-123"),
        ):
            assert api_key.ensure_api_key() is True
        assert "sk-new-key-123" in env_file.read_text(encoding="utf-8")

    def test_empty_input_returns_false(self):
        import src.cli.api_key as api_key
        with (
            patch.object(api_key, "_current_key", return_value=""),
            patch.object(api_key, "_is_tty", return_value=True),
            patch.object(api_key, "_prompt_for_key", return_value=None),
        ):
            assert api_key.ensure_api_key() is False
