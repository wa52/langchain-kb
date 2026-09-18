import io
import os
from pathlib import Path
import sys


def _wrap_utf8(stream):
    if hasattr(stream, "buffer"):
        return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
    return stream


def run_cli():
    from src.cli.knowledge import app
    app()


def _reexec_server_in_project_venv() -> None:
    """Run Web/API commands in the project runtime instead of global Python.

    The global ``knowledge`` launcher is intentionally lightweight. Keeping the
    actual server inside ``kb_env`` prevents unrelated globally installed MCP
    applications from forcing an incompatible SDK version into this service.
    """
    if len(sys.argv) < 2 or sys.argv[1] not in {"web", "serve"} or "--stop" in sys.argv:
        return
    if os.getenv("KNOWLEDGE_RUNTIME_REEXEC") == "1":
        return
    from config import PROJECT_ROOT

    runtime = Path(PROJECT_ROOT) / "kb_env" / "Scripts" / "python.exe"
    if not runtime.is_file() or Path(sys.executable).resolve() == runtime.resolve():
        return
    environment = os.environ.copy()
    environment["KNOWLEDGE_RUNTIME_REEXEC"] = "1"
    os.chdir(PROJECT_ROOT)
    os.execve(
        str(runtime),
        [str(runtime), "-m", "src.cli.entry", *sys.argv[1:]],
        environment,
    )


def main():
    sys.stdout = _wrap_utf8(sys.stdout)
    sys.stderr = _wrap_utf8(sys.stderr)
    _reexec_server_in_project_venv()
    from config import ensure_data_dirs
    ensure_data_dirs()
    run_cli()


if __name__ == "__main__":
    main()
