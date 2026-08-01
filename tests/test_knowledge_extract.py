import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.ingestion.knowledge_extract import (
    extract_hdev,
    extract_code,
    extract_document,
)

_HDEV_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<hdevelop file_version="1.2" halcon_version="24.11.1.0">
<procedure name="main">
<interface/>
<body>
<c>* Initialize visualization</c>
<l>dev_update_off ()</l>
<l>read_image (Image, 'fabrik')</l>
<l>threshold (Image, Region, 0, 128)</l>
</body>
<docu id="main"><parameters/></docu>
</procedure>
<procedure name="process_image">
<interface/>
<body>
<c>* Process the image</c>
<l>connection (Region, ConnectedRegions)</l>
</body>
</procedure>
</hdevelop>
"""


class TestExtractHdev:
    def test_extracts_operator_chain(self):
        out = extract_hdev(_HDEV_SAMPLE)
        assert "read_image" in out
        assert "threshold" in out
        assert "dev_update_off" in out

    def test_includes_procedure_names(self):
        out = extract_hdev(_HDEV_SAMPLE)
        assert "main" in out
        assert "process_image" in out

    def test_includes_comments(self):
        out = extract_hdev(_HDEV_SAMPLE)
        assert "Initialize visualization" in out
        assert "Process the image" in out

    def test_output_is_markdown_structured(self):
        out = extract_hdev(_HDEV_SAMPLE)
        assert out.startswith("#")
        assert "算子调用链" in out or "算子" in out

    def test_handles_operator_with_args(self):
        out = extract_hdev(_HDEV_SAMPLE)
        assert "Region" in out


class TestExtractCode:
    def test_extracts_functions(self):
        code = (
            "/*\\n"
            " * Demo: read an image and threshold it\\n"
            " */\\n"
            "int main() {\\n"
            "  read_image(&ho_Image, \"fabrik\");\\n"
            "  return 0;\\n"
            "}\\n"
        )
        out = extract_code(code)
        assert "main" in out
        assert "read_image" in out

    def test_extracts_head_comments(self):
        code = "# include <stdio.h>\n# Demo program\nint foo(void) { return 0; }\n"
        out = extract_code(code)
        assert "Demo program" in out

    def test_cpp_class_detection(self):
        code = "class MyApp {\npublic:\n  void run();\n};\n"
        out = extract_code(code)
        assert "MyApp" in out


class TestExtractDocument:
    def test_markdown_passthrough(self):
        text = "# 标题\n\n正文内容。"
        assert extract_document("a.md", text, ".md") == text

    def test_txt_passthrough(self):
        text = "纯文本内容。"
        assert extract_document("a.txt", text, ".txt") == text

    def test_unknown_extension_passthrough(self):
        text = "whatever"
        assert extract_document("a.xyz", text, ".xyz") == text

    def test_hdev_dispatches(self):
        out = extract_document("a.hdev", _HDEV_SAMPLE, ".hdev")
        assert "read_image" in out

    def test_code_dispatches(self):
        code = "int main() { read_image(&h, \"x\"); }\n"
        out = extract_document("a.c", code, ".c")
        assert "read_image" in out


class TestLoadPathImages:
    def test_image_files_not_indexed(self):
        from src.ingestion.loader import load_path
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            (d / "image.png").write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 64)
            (d / "image.jpg").write_bytes(b"\xff\xd8\xff" + b"0" * 64)
            (d / "doc.md").write_text("# hello", encoding="utf-8")
            mock = MagicMock()
            docs = load_path(d, echo_fn=mock)
            sources = [doc.metadata.get("source", "") for doc in docs]
            assert len(docs) == 1
            assert "doc.md" in sources[0]

    def test_source_uses_relative_path(self):
        from src.ingestion.loader import load_path
        with tempfile.TemporaryDirectory() as td:
            d = Path(td)
            sub = d / "sub" / "deep"
            sub.mkdir(parents=True)
            (sub / "a.hdev").write_text(_HDEV_SAMPLE, encoding="utf-8")
            mock = MagicMock()
            docs = load_path(d, echo_fn=mock)
            assert len(docs) == 1
            src = docs[0].metadata.get("source", "")
            assert src == str(Path("sub") / "deep" / "a.hdev")
