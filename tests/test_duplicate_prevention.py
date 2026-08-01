import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ingestion.pipeline import run_add_path


class TestDuplicatePrevention:
    def test_repeat_add_file_skipped(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "seg.hdev"
            src.write_text(
                "<hdevelop><procedure name=\"main\"><body><l>read_image (Image, 'x')</l></body></procedure></hdevelop>",
                encoding="utf-8",
            )
            ext = root / "external"
            # isolate tracker to temp
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")

            try:
                c1 = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                c2 = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                dirs = [p.name for p in ext.iterdir() if p.is_dir()]
                files = [p.name for p in ext.rglob("*.hdev")]
                assert c1 > 0
                assert c2 == 0, "重复添加应返回 0"
                assert len(files) == 1, "不应产生重复副本"
            finally:
                tr.TRACKER_FILE = orig

    def test_repeat_add_dir_skipped(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "demo"
            src.mkdir()
            (src / "a.hdev").write_text(
                "<hdevelop><procedure name=\"main\"><body><l>read_image (Image, 'x')</l></body></procedure></hdevelop>",
                encoding="utf-8",
            )
            ext = root / "external"
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")

            try:
                c1 = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                c2 = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                dirs = [p.name for p in ext.iterdir() if p.is_dir()]
                assert c1 > 0
                assert c2 == 0, "重复目录添加应返回 0"
                assert len(dirs) == 1, f"不应产生重复目录: {dirs}"
            finally:
                tr.TRACKER_FILE = orig
