from pathlib import Path
from unittest.mock import patch


def test_web_command_reexecs_into_project_venv(monkeypatch, tmp_path):
    from src.cli.entry import _reexec_server_in_project_venv

    runtime = tmp_path / "kb_env" / "Scripts" / "python.exe"
    runtime.parent.mkdir(parents=True)
    runtime.touch()
    monkeypatch.setattr("sys.argv", ["knowledge", "web", "--no-open"])
    monkeypatch.delenv("KNOWLEDGE_RUNTIME_REEXEC", raising=False)

    with (
        patch("config.PROJECT_ROOT", tmp_path),
        patch("sys.executable", str(tmp_path / "global" / "python.exe")),
        patch("os.chdir") as chdir,
        patch("os.execve") as execve,
    ):
        _reexec_server_in_project_venv()

    chdir.assert_called_once_with(tmp_path)
    executable, args, environment = execve.call_args.args
    assert Path(executable) == runtime
    assert args == [str(runtime), "-m", "src.cli.entry", "web", "--no-open"]
    assert environment["KNOWLEDGE_RUNTIME_REEXEC"] == "1"
