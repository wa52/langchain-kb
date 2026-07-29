#!/usr/bin/env python
import sys
import io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

from src.cli.commands import cli
from src.cli.console import run_console

if __name__ == "__main__":
    if len(sys.argv) == 1:
        run_console()
    else:
        cli()
