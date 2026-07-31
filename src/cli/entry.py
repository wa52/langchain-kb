import io
import sys


def _wrap_utf8(stream):
    if hasattr(stream, "buffer"):
        return io.TextIOWrapper(stream.buffer, encoding="utf-8", errors="replace")
    return stream


def run_cli():
    from src.cli.knowledge import app
    app()


def main():
    sys.stdout = _wrap_utf8(sys.stdout)
    sys.stderr = _wrap_utf8(sys.stderr)
    run_cli()


if __name__ == "__main__":
    main()
