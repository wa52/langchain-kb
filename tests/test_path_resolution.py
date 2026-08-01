from pathlib import Path

import pytest


class TestPathsFollowKnowledgeHome:
    def test_history_dir_anchors_to_knowledge_home(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "KNOWLEDGE_HOME", tmp_path)
        monkeypatch.delenv("CHAT_HISTORY_DIR", raising=False)
        import importlib
        import src.agent.chat_history as ch
        importlib.reload(ch)
        assert ch.HISTORY_DIR == tmp_path / "data" / "chat_history"

    def test_history_dir_env_override(self, tmp_path, monkeypatch):
        import src.agent.chat_history as ch
        monkeypatch.setenv("CHAT_HISTORY_DIR", str(tmp_path / "custom"))
        import importlib
        importlib.reload(ch)
        assert ch.HISTORY_DIR == tmp_path / "custom"
        # save+list round-trip writes into the overridden dir
        ch.save_history([{"role": "user", "content": "hi"}], "sess_env")
        assert (tmp_path / "custom" / "sess_env.json").exists()

    def test_tracker_anchors_to_knowledge_home(self, tmp_path, monkeypatch):
        import config
        monkeypatch.setattr(config, "KNOWLEDGE_HOME", tmp_path)
        monkeypatch.delenv("FILE_TRACKER_PATH", raising=False)
        import importlib
        import src.ingestion.tracker as tr
        importlib.reload(tr)
        assert Path(tr.TRACKER_FILE) == tmp_path / "data" / "file_tracker.json"

    def test_tracker_env_override(self, tmp_path, monkeypatch):
        import src.ingestion.tracker as tr
        monkeypatch.setenv("FILE_TRACKER_PATH", str(tmp_path / "custom.json"))
        import importlib
        importlib.reload(tr)
        assert tr.TRACKER_FILE == str(tmp_path / "custom.json")
