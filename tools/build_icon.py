"""Render the project SVG into a multi-resolution Windows shortcut icon.

Build-time only: run with a Python environment containing PySide6 and Pillow.
"""

from pathlib import Path

from PIL import Image
from PySide6.QtCore import Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web" / "public" / "assets" / "knowledge-agent.svg"
TARGET = ROOT / "assets" / "knowledge-agent.ico"


def main() -> None:
    renderer = QSvgRenderer(str(SOURCE))
    if not renderer.isValid():
        raise RuntimeError(f"Invalid SVG: {SOURCE}")

    canvas = QImage(512, 512, QImage.Format.Format_ARGB32)
    canvas.fill(Qt.GlobalColor.transparent)
    painter = QPainter(canvas)
    try:
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        renderer.render(painter)
    finally:
        painter.end()

    image = Image.frombytes(
        "RGBA", (canvas.width(), canvas.height()),
        bytes(canvas.bits()), "raw", "BGRA",
    )
    TARGET.parent.mkdir(parents=True, exist_ok=True)
    image.save(TARGET, format="ICO", sizes=[(size, size) for size in (16, 24, 32, 48, 64, 128, 256)])
    print(TARGET)


if __name__ == "__main__":
    main()
