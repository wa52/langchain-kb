#!/usr/bin/env python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from src.cli.commands import cli
from src.cli.console import run_console
from config import ensure_data_dirs


def run_api():
    import uvicorn
    from src.api.app import app
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="info")


if __name__ == "__main__":
    ensure_data_dirs()
    if len(sys.argv) >= 2 and sys.argv[1] == "api":
        sys.argv.pop(1)
        run_api()
    elif len(sys.argv) >= 2 and sys.argv[1] == "kb":
        sys.argv.pop(1)
        from src.cli.kb import kb
        kb()
    elif len(sys.argv) >= 2 and sys.argv[1] == "knowledge":
        sys.argv.pop(1)
        from src.cli.knowledge import app
        app()
    elif len(sys.argv) == 1:
        run_console()
    else:
        cli()
