from pathlib import Path
from langchain_core.documents import Document


def _source_name(doc) -> str:
    return Path(doc.metadata.get("source", "")).name


def _make_pdf_loader(path: str | Path):
    from langchain_community.document_loaders import PyMuPDFLoader
    return PyMuPDFLoader(str(path))


_TEXT_EXTS = {".md", ".txt"}
_PDF_EXTS = {".pdf"}
_CODE_EXTS = {".c", ".cpp", ".cs", ".vb", ".py", ".h", ".hpp"}
_HDEV_EXTS = {".hdev"}
_ALL_EXTS = _TEXT_EXTS | _PDF_EXTS | _CODE_EXTS | _HDEV_EXTS


def _iter_files(data_dir: Path):
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() not in _ALL_EXTS:
            continue
        if path.stem.startswith("~$"):
            continue
        yield path


def _read_text(path: Path) -> str:
    """Read a text file tolerantly. Strict UTF-8 is tried first. When it fails,
    the file is usually one of two cases:

    - a UTF-8 file with a few corrupt bytes (PDF-extracted manuals): keep
      UTF-8-with-replacement so the readable Chinese/English survives;
    - a genuinely GBK/GB18030 encoded doc: UTF-8-lossy turns nearly every byte
      into a replacement char, so fall through to GB18030/UTF-16/Latin-1.

    The replacement-char ratio cleanly separates the two (real UTF-8 files stay
    well under 30%; a GBK file comes out mostly replacement chars)."""
    raw = path.read_bytes()
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass
    lossy = raw.decode("utf-8", errors="replace")
    if lossy.count("\ufffd") / max(1, len(lossy)) < 0.30:
        return lossy
    for enc in ("gb18030", "utf-16", "latin-1"):
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return lossy


def _load_file(path: Path, base_dir: Path | None = None) -> list:
    from src.ingestion.knowledge_extract import extract_document

    suffix = path.suffix.lower()
    if suffix in _CODE_EXTS or suffix in _HDEV_EXTS:
        text = _read_text(path)
        enhanced = extract_document(path, text, suffix)
        docs = [Document(page_content=enhanced, metadata={})]
    elif suffix in _TEXT_EXTS:
        docs = [Document(page_content=_read_text(path), metadata={})]
    elif suffix in _PDF_EXTS:
        docs = _make_pdf_loader(path).load()
    else:
        return []
    source = str(path.relative_to(base_dir)) if base_dir else path.name
    for doc in docs:
        doc.metadata["source"] = source
    return docs


class MarkdownLoader:
    def __init__(self, data_dir: str | Path, echo_fn: callable = print):
        self.data_dir = Path(data_dir)
        self.echo_fn = echo_fn

    def load_all(self) -> list:
        all_files = list(_iter_files(self.data_dir))
        docs = []
        for i, f in enumerate(all_files):
            docs.extend(_load_file(f, base_dir=self.data_dir))
            if (i + 1) % 20 == 0 or i == len(all_files) - 1:
                self.echo_fn(f"\r  [{i+1}/{len(all_files)}] 已加载 {len(docs)} 个文档", end="")
        self.echo_fn()
        return docs


def load_path(path: str | Path, echo_fn: callable = print) -> list:
    path = Path(path)
    if path.is_file():
        return _load_file(path)
    elif path.is_dir():
        all_files = list(_iter_files(path))
        docs = []
        for i, f in enumerate(all_files):
            docs.extend(_load_file(f, base_dir=path))
            if (i + 1) % 20 == 0 or i == len(all_files) - 1:
                echo_fn(f"\r  [{i+1}/{len(all_files)}] 已加载 {len(docs)} 个文档", end="")
        if all_files:
            echo_fn()
        return docs
    return []


def load_files(paths: list[str | Path], base_dir: str | Path, echo_fn: callable = print) -> list:
    """Load an explicit set of files, with sources relative to ``base_dir``.

    Unlike ``load_path`` this does not scan the directory, so a stale leftover
    from a previously failed copy is never picked up and indexed twice."""
    base = Path(base_dir)
    docs = []
    for i, f in enumerate(paths):
        docs.extend(_load_file(Path(f), base_dir=base))
        if (i + 1) % 20 == 0 or i == len(paths) - 1:
            echo_fn(f"\r  [{i+1}/{len(paths)}] 已加载 {len(docs)} 个文档", end="")
    if paths:
        echo_fn()
    return docs
