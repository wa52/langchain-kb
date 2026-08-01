"""Knowledge-ization of ingested documents.

Transforms raw file contents (HALCON .hdev programs, source code) into
structured, searchable Markdown knowledge text before chunking. Plain
documents (.md/.txt/.pdf) and unknown formats pass through unchanged.
"""

import re
from pathlib import Path
from xml.etree import ElementTree

_HDEV_EXTS = {".hdev"}
_CODE_EXTS = {".c", ".cpp", ".cs", ".vb", ".py", ".h", ".hpp"}


def extract_hdev(xml_text: str) -> str:
    """Parse a HALCON .hdev (XML) and produce a structured Markdown summary.

    Extracts each <procedure> block: its name, <c> comments, and <l> operator
    call lines, rendered as a numbered operator chain.
    """
    try:
        root = ElementTree.fromstring(xml_text)
    except ElementTree.ParseError:
        return _raw_hdev(xml_text)

    lines: list[str] = []
    halcon_version = root.get("halcon_version", "")
    title = f"HALCON 例程（HDevelop）"
    if halcon_version:
        title += f" - 版本 {halcon_version}"
    lines.append(f"# {title}")

    procedures = root.findall("procedure")
    if not procedures:
        return _raw_hdev(xml_text)

    for proc in procedures:
        name = proc.get("name", "")
        if name:
            lines.append(f"\n## 过程: {name}")

        body = proc.find("body")
        if body is None:
            continue

        comments: list[str] = []
        operators: list[str] = []
        for child in body:
            tag = child.tag
            text = (child.text or "").strip()
            if not text:
                continue
            if tag == "c":
                comments.append(text)
            elif tag == "l":
                operators.append(text)

        if comments:
            lines.append("\n### 注释")
            for c in comments:
                lines.append(f"- {c}")

        if operators:
            lines.append("\n### 算子调用链")
            for i, op in enumerate(operators, 1):
                lines.append(f"{i}. {op}")

    return "\n".join(lines)


def _raw_hdev(xml_text: str) -> str:
    """Fallback: strip XML tags to plain operator lines."""
    text = re.sub(r"<[^>]+>", "\n", xml_text)
    text = re.sub(r"\n{2,}", "\n", text)
    return text.strip() or "HALCON 例程（HDevelop）"


def extract_code(text: str) -> str:
    """Extract knowledge from source code via language-agnostic heuristics:
    head comment blocks, function/class names, and call statements."""
    head_comments = _extract_head_comments(text)
    symbols = _extract_symbols(text)
    calls = _extract_calls(text)

    out: list[str] = ["# 代码文件知识概览"]
    if head_comments:
        out.append("\n## 文件头注释")
        out.append(head_comments.strip())
    if symbols:
        out.append("\n## 关键符号")
        for s in symbols:
            out.append(f"- {s}")
    if calls:
        out.append("\n## API / 函数调用")
        for c in calls:
            out.append(f"- {c}")
    return "\n".join(out)


def _extract_head_comments(text: str) -> str:
    # Block comment at the very start: /* ... */ (possibly spanning lines)
    m = re.match(r"^\s*/\*.*?\*/", text, re.DOTALL)
    if m:
        return _strip_block_comment_markers(m.group(0))
    # Consecutive // or # comment lines at the start
    head_lines = []
    for line in text.splitlines()[:30]:
        stripped = line.strip()
        if stripped.startswith("//") or stripped.startswith("#"):
            head_lines.append(stripped.lstrip("#/").strip())
        elif not stripped and head_lines:
            continue
        elif head_lines and not stripped.startswith("//") and not stripped.startswith("#"):
            break
        elif not stripped:
            continue
        else:
            break
    return "\n".join(head_lines)


def _strip_block_comment_markers(block: str) -> str:
    lines = []
    for line in block.splitlines():
        s = line.strip()
        if not s:
            continue
        s = s.lstrip("/").strip()
        s = s.rstrip("/").strip()
        s = s.strip("*").strip()
        if s:
            lines.append(s)
    return "\n".join(lines)


def _extract_symbols(text: str) -> list[str]:
    symbols: list[str] = []
    for pat in (r"^class\s+(\w+)", r"^def\s+(\w+)", r"\b(?:int|void|double|char|bool|float|HObject)\s+(\w+)\s*\("):
        for m in re.finditer(pat, text, re.MULTILINE):
            name = m.group(1)
            if name not in symbols:
                symbols.append(name)
    return symbols[:50]


def _extract_calls(text: str) -> list[str]:
    calls: list[str] = []
    for m in re.finditer(r"\b([a-zA-Z_]\w*)\s*\(", text):
        name = m.group(1)
        # Skip common control keywords and declarations
        if name in {"if", "for", "while", "switch", "return", "sizeof", "new",
                     "int", "void", "double", "char", "bool", "float"}:
            continue
        if name in calls:
            continue
        calls.append(name + "()")
    return calls[:50]


def extract_document(path, text: str, ext: str) -> str:
    """Route a file to the right knowledge-ization adapter.

    Returns transformed knowledge text for code/hdev, or the original text
    for plain documents and unknown formats (fail-safe pass-through).
    """
    ext = (ext or Path(path).suffix).lower()
    if ext in _HDEV_EXTS:
        return extract_hdev(text)
    if ext in _CODE_EXTS:
        return extract_code(text)
    return text
