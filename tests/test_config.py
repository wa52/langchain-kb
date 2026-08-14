import importlib
import os
import sys
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


class TestWheelDeploymentDefaults:

    def test_site_packages_falls_back_to_platform_data_home(self, monkeypatch, tmp_path):
        """When config.py is installed under site-packages (wheel install),
        the knowledge base root defaults to the platform application data
        directory (not the CWD), so upgrades never overwrite user data."""
        import sysconfig
        purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
        fake_site = purelib / "site-packages" / "personal_knowledge_base"
        monkeypatch.setattr(config, "PROJECT_ROOT", fake_site)
        monkeypatch.delenv("KNOWLEDGE_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        result = config._default_knowledge_home()
        assert result == config._platform_data_home()
        assert result.is_absolute()
        assert result != tmp_path.resolve()

    def test_platform_data_home_windows(self, monkeypatch, tmp_path):
        if sys.platform != "win32":
            pytest.skip("windows only")
        monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "AppData" / "Local"))
        assert config._platform_data_home() == (
            tmp_path / "AppData" / "Local" / "KnowledgeAgent"
        ).resolve()

    def test_platform_data_home_linux_xdg(self, monkeypatch, tmp_path):
        if sys.platform in ("win32", "darwin"):
            pytest.skip("posix-only")
        monkeypatch.delenv("LOCALAPPDATA", raising=False)
        monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
        assert config._platform_data_home() == (tmp_path / "xdg" / "knowledge-agent").resolve()

    def test_site_packages_but_env_set_uses_env(self, monkeypatch, tmp_path):
        import sysconfig
        purelib = Path(sysconfig.get_paths()["purelib"]).resolve()
        fake_site = purelib / "site-packages" / "personal_knowledge_base"
        monkeypatch.setattr(config, "PROJECT_ROOT", fake_site)
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path / "kb"))
        monkeypatch.chdir(tmp_path)
        assert config._default_knowledge_home() == (tmp_path / "kb").resolve()

    def test_dev_checkout_uses_project_root(self, monkeypatch, tmp_path):
        """Development checkout (not under site-packages) keeps the project
        root as the default regardless of the working directory."""
        monkeypatch.setattr(config, "PROJECT_ROOT", Path("D:/proj/langchain-kb"))
        monkeypatch.delenv("KNOWLEDGE_HOME", raising=False)
        monkeypatch.chdir(tmp_path)
        assert config._default_knowledge_home() == Path("D:/proj/langchain-kb").resolve()


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


class TestDataDirDefault:

    def test_data_dir_defaults_to_knowledge_home_data_docs(
            self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.delenv("DATA_DIR", raising=False)
        importlib.reload(config)
        assert config.DATA_DIR == tmp_path / "data" / "docs"

    def test_data_dir_explicit_absolute_respected(
            self, fresh_config, tmp_path, monkeypatch):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        monkeypatch.setenv("DATA_DIR", "D:/real/docs")
        importlib.reload(config)
        assert config.DATA_DIR == Path("D:/real/docs")


class TestEnsureDataDirs:

    def _fresh_home(self, monkeypatch, tmp_path):
        monkeypatch.setenv("KNOWLEDGE_HOME", str(tmp_path))
        for key in ["DATA_DIR", "CHROMA_PERSIST_DIR", "EXTERNAL_DIR", "GRAPH_PERSIST_DIR"]:
            monkeypatch.delenv(key, raising=False)

    def test_creates_directory_skeleton(self, fresh_config, tmp_path, monkeypatch):
        self._fresh_home(monkeypatch, tmp_path)
        importlib.reload(config)
        config.ensure_data_dirs()
        assert (tmp_path / "chroma_db").is_dir()
        assert (tmp_path / "data" / "external").is_dir()
        assert (tmp_path / "data" / "docs").is_dir()

    def test_idempotent(self, fresh_config, tmp_path, monkeypatch):
        self._fresh_home(monkeypatch, tmp_path)
        importlib.reload(config)
        config.ensure_data_dirs()
        config.ensure_data_dirs()
        assert (tmp_path / "data" / "docs").is_dir()
