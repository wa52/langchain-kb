import sys
from pathlib import Path

import pytest


class TestEntryModule:

    def test_entry_exports_main_and_run_cli(self):
        from src.cli import entry
        assert callable(entry.main)
        assert callable(entry.run_cli)

    def test_run_cli_dispatches_to_knowledge_app(self, monkeypatch, capsys):
        from src.cli import entry
        monkeypatch.setattr(sys, "argv", ["knowledge", "--help"])
        with pytest.raises(SystemExit) as exc:
            entry.run_cli()
        assert exc.value.code == 0
        out = capsys.readouterr().out
        assert "serve" in out
        assert "search" in out

    def test_main_ensures_data_dirs_then_runs(self):
        import subprocess
        import sys as _sys
        code = (
            "import sys\n"
            "from unittest.mock import patch\n"
            "from src.cli import entry\n"
            "sys.argv = ['knowledge', 'status']\n"
            "with patch('src.cli.entry.run_cli') as m_run, \\\n"
            "        patch('config.ensure_data_dirs') as m_ensure:\n"
            "    entry.main()\n"
            "    m_ensure.assert_called_once()\n"
            "    m_run.assert_called_once()\n"
            "print('OK')\n"
        )
        proc = subprocess.run([_sys.executable, "-c", code], capture_output=True, text=True)
        assert proc.returncode == 0, proc.stderr
        assert "OK" in proc.stdout


class TestPackaging:

    def test_pyproject_declares_knowledge_script(self):
        root = Path(__file__).resolve().parent.parent
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert '[project.scripts]' in text
        assert 'knowledge = "src.cli.entry:main"' in text

    def test_pyproject_packages_src_and_config(self):
        root = Path(__file__).resolve().parent.parent
        text = (root / "pyproject.toml").read_text(encoding="utf-8")
        assert "config" in text
        assert "src*" in text
