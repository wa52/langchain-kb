#!/usr/bin/env python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.cli.commands import cli
from src.cli.console import run_console


def run_api():
    import uvicorn
    from src.api.app import app
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")


if __name__ == "__main__":
    if len(sys.argv) >= 2 and sys.argv[1] == "api":
        sys.argv.pop(1)
        run_api()
    elif len(sys.argv) == 1:
        run_console()
    else:
        cli()
