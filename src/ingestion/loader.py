from pathlib import Path
from langchain_community.document_loaders import DirectoryLoader, TextLoader


def _source_name(doc) -> str:
    return Path(doc.metadata.get("source", "")).name


def _make_pdf_loader(path: str | Path):
    from langchain_community.document_loaders import PyMuPDFLoader
    return PyMuPDFLoader(str(path))


_TEXT_EXTS = {".md", ".txt"}
_PDF_EXTS = {".pdf"}
_ALL_EXTS = _TEXT_EXTS | _PDF_EXTS


def _iter_files(data_dir: Path):
    for path in data_dir.rglob("*"):
        if not path.is_file():
            continue
        if path.suffix.lower() in _ALL_EXTS:
            yield path


def _load_file(path: Path, base_dir: Path | None = None) -> list:
    suffix = path.suffix.lower()
    if suffix in _TEXT_EXTS:
        docs = TextLoader(str(path), encoding="utf-8").load()
    elif suffix in _PDF_EXTS:
        docs = _make_pdf_loader(path).load()
    else:
        return []
    for doc in docs:
        doc.metadata["source"] = path.name
    return docs


class MarkdownLoader:
    def __init__(self, data_dir: str | Path, echo_fn: callable = print):
        self.data_dir = Path(data_dir)
        self.echo_fn = echo_fn

    def load_all(self) -> list:
        all_files = list(_iter_files(self.data_dir))
        docs = []
        for i, f in enumerate(all_files):
            docs.extend(_load_file(f))
            if (i + 1) % 20 == 0 or i == len(all_files) - 1:
                self.echo_fn(f"\r  [{i+1}/{len(all_files)}] 已加载 {len(docs)} 个文档", end="")
        self.echo_fn()
        return docs


def load_path(path: str | Path) -> list:
    path = Path(path)
    if path.is_file():
        return _load_file(path)
    elif path.is_dir():
        docs = []
        for f in _iter_files(path):
            docs.extend(_load_file(f))
        return docs
    return []
