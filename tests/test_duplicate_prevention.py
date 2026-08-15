import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.ingestion.pipeline import run_add_path


class TestDuplicatePrevention:
    @pytest.fixture(autouse=True)
    def _isolate_store(self):
        # run_add_path would otherwise run the real embedding load, write to
        # the real chroma_db and real knowledge_graph.json, and rebuild the
        # real BM25 pickle. These tests only exercise the tracker/dedup logic.
        # Note: add_documents_with_progress() reaches the store through
        # chroma_client.get_vector_store(), so BOTH bindings must be stubbed.
        patches = [
            patch("src.ingestion.pipeline.get_vector_store", return_value=MagicMock()),
            patch("src.vector_store.chroma_client.get_vector_store", return_value=MagicMock()),
            patch("src.ingestion.pipeline.get_embedding_model", return_value=MagicMock()),
            patch("src.ingestion.pipeline.rebuild_bm25"),
            patch("src.graph_store.graph.KnowledgeGraph", return_value=MagicMock()),
            patch("src.graph_store.retriever.set_graph"),
        ]
        for p in patches:
            p.start()
        yield
        for p in patches:
            p.stop()

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

    def test_add_file_skips_exact_content_duplicate(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ext = root / "external"
            ext.mkdir()
            existing = ext / "existing.md"
            existing.write_text("重复内容XYZ", encoding="utf-8")
            new_file = root / "new.md"
            new_file.write_text("重复内容XYZ", encoding="utf-8")
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")
            tr.update_tracker("external", ext, [str(existing)])

            try:
                c = run_add_path(str(new_file), str(ext), echo_fn=lambda *a, **k: None)
                files = [p.name for p in ext.rglob("*.md")]
                assert c == 0, "相同内容不应重复添加"
                assert files == ["existing.md"], f"不应产生内容重复副本: {files}"
            finally:
                tr.TRACKER_FILE = orig

    def test_add_dir_skips_exact_content_duplicate(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ext = root / "external"
            ext.mkdir()
            existing = ext / "existing.md"
            existing.write_text("重复内容XYZ", encoding="utf-8")
            src = root / "src"
            src.mkdir()
            (src / "rename.md").write_text("重复内容XYZ", encoding="utf-8")
            (src / "unique.md").write_text("新内容", encoding="utf-8")
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")
            tr.update_tracker("external", ext, [str(existing)])

            try:
                c = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                copied = sorted(str(p.relative_to(ext)).replace("\\", "/") for p in ext.rglob("*.md"))
                assert c > 0
                assert "src/unique.md" in copied
                assert "src/rename.md" not in copied, "相同内容不应被重复复制"
                assert "existing.md" in copied
            finally:
                tr.TRACKER_FILE = orig

    def test_add_dir_excludes_subtree(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ext = root / "external"
            ext.mkdir()
            src = root / "src"
            src.mkdir()
            (src / "keep.md").write_text("保留", encoding="utf-8")
            halcon = src / "manuals" / "Technology" / "HALCON"
            halcon.mkdir(parents=True)
            (halcon / "skip.md").write_text("跳过", encoding="utf-8")
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")

            try:
                c = run_add_path(
                    str(src),
                    str(ext),
                    echo_fn=lambda *a, **k: None,
                    exclude=["manuals/Technology/HALCON"],
                )
                copied = sorted(str(p.relative_to(ext)).replace("\\", "/") for p in ext.rglob("*.md"))
                assert c > 0
                assert "src/keep.md" in copied
                assert not any("HALCON" in p for p in copied), f"排除的子树不应被复制: {copied}"
            finally:
                tr.TRACKER_FILE = orig

    def test_add_dir_reuses_stale_target_no_rename(self):
        import src.ingestion.tracker as tr
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            ext = root / "external"
            ext.mkdir()
            # leftover from a previously failed add: copied but never tracked
            stale = ext / "src"
            stale.mkdir()
            (stale / "old.md").write_text("旧残留", encoding="utf-8")
            src = root / "src"
            src.mkdir()
            (src / "a.md").write_text("新内容A", encoding="utf-8")
            orig = tr.TRACKER_FILE
            tr.TRACKER_FILE = str(root / "file_tracker.json")

            try:
                c = run_add_path(str(src), str(ext), echo_fn=lambda *a, **k: None)
                dirs = sorted(d.name for d in ext.iterdir() if d.is_dir())
                assert c > 0
                assert dirs == ["src"], f"不应产生 _1 克隆目录: {dirs}"
                assert (stale / "a.md").exists(), "新文件应补充进已有副本"
            finally:
                tr.TRACKER_FILE = orig
