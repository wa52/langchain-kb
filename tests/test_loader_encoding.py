import tempfile
from pathlib import Path

from src.ingestion.loader import load_path


class TestLoaderEncoding:
    def test_load_gbk_md_file(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "手册.md"
            p.write_bytes("这是中文手册。\n第二行内容。".encode("gbk"))
            docs = load_path(p)
            assert len(docs) == 1
            assert "这是中文手册" in docs[0].page_content
            assert docs[0].metadata["source"] == "手册.md"

    def test_load_dir_mixed_encodings(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            (root / "gbk.md").write_bytes("中文A".encode("gbk"))
            (root / "utf8.md").write_text("plain utf8", encoding="utf-8")
            docs = load_path(root)
            texts = [d.page_content for d in docs]
            assert len(docs) == 2
            assert "中文A" in texts
            assert "plain utf8" in texts

    def test_load_utf8_with_corrupt_byte(self):
        # mostly-valid UTF-8 with one corrupt byte must stay readable Chinese,
        # not be mis-decoded as GBK/GB18030 (which accepts almost any bytes).
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "manual.md"
            raw = bytearray("算法平台用户手册".encode("utf-8"))
            raw[8] = 0xFF  # corrupt one byte inside the UTF-8 sequence
            p.write_bytes(bytes(raw))
            docs = load_path(p)
            assert len(docs) == 1
            assert "算法平台用户手册" in docs[0].page_content or "算法" in docs[0].page_content
