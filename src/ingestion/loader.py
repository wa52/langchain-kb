from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader, TextLoader
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


def _read_utf8(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def _load_file(path: Path, base_dir: Path | None = None) -> list:
    from src.ingestion.knowledge_extract import extract_document

    suffix = path.suffix.lower()
    if suffix in _CODE_EXTS or suffix in _HDEV_EXTS:
        text = _read_utf8(path)
        enhanced = extract_document(path, text, suffix)
        docs = [Document(page_content=enhanced, metadata={})]
    elif suffix in _TEXT_EXTS:
        docs = TextLoader(str(path), encoding="utf-8").load()
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
