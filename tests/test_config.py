import importlib
import os
from pathlib import Path

import pytest

import config

CONFIG_PATHS = [
    "KNOWLEDGE_HOME", "DATA_DIR", "CHROMA_PERSIST_DIR",
    "EXTERNAL_DIR", "GRAPH_PERSIST_DIR",
]


@pytest.fixture
def fresh_config(monkeypatch):
    saved = {k: os.environ.get(k) for k in CONFIG_PATHS}
    yield importlib.reload(config)
    for k, v in saved.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    importlib.reload(config)


class TestKnowledgeHome:

    def test_defaults_to_project_root(self, fresh_config):
        expected = Path(config.__file__).resolve().parent
        assert config.KNOWLEDGE_HOME == expected

    def test_env_override(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        importlib.reload(config)
        assert config.KNOWLEDGE_HOME == tmp_path.resolve()

    def test_is_absolute(self, fresh_config):
        assert Path(config.KNOWLEDGE_HOME).is_absolute()


class TestRelativePathResolution:

    def test_chroma_persist_dir_resolves_against_home(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("CHROMA_PERSIST_DIR", "./chroma_db")
        importlib.reload(config)
        assert config.CHROMA_PERSIST_DIR == str(tmp_path / "chroma_db")

    def test_external_dir_resolves_against_home(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("EXTERNAL_DIR", "./data/external")
        importlib.reload(config)
        assert config.EXTERNAL_DIR == str(tmp_path / "data" / "external")

    def test_graph_persist_dir_resolves_against_home(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("GRAPH_PERSIST_DIR", "./data")
        importlib.reload(config)
        assert config.GRAPH_PERSIST_DIR == str(tmp_path / "data")

    def test_relative_data_dir_resolves_against_home(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("DATA_DIR", "docs")
        importlib.reload(config)
        assert config.DATA_DIR == tmp_path / "docs"

    def test_absolute_paths_kept(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("CHROMA_PERSIST_DIR", "D:/abs/chroma_db")
        importlib.reload(config)
        assert Path(config.CHROMA_PERSIST_DIR) == Path("D:/abs/chroma_db")


class TestCwdIndependence:

    def test_default_paths_not_relative_to_cwd(self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        importlib.reload(config)
        for key in ["CHROMA_PERSIST_DIR", "EXTERNAL_DIR", "GRAPH_PERSIST_DIR"]:
            value = getattr(config, key)
            assert Path(value).is_absolute()
            assert str(tmp_path) not in value
        assert config.KNOWLEDGE_HOME == Path(config.__file__).resolve().parent
