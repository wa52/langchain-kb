import hashlib
import shutil
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE
from src.ingestion.loader import MarkdownLoader, load_files, load_path
from src.ingestion.splitter import create_splitter
from src.ingestion.tracker import get_changed_files, update_tracker, remove_from_tracker
from src.retrieval.retriever import rebuild_bm25
from src.vector_store.chroma_client import get_vector_store, reset_vector_store, delete_by_source, add_documents_with_progress
from src.vector_store.embedding import get_embedding_model

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".jp2", ".webp"}


def _file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(65536), b""):
            digest.update(block)
    return digest.hexdigest()


def _existing_by_size(base_dir: Path) -> dict[int, list[Path]]:
    """Every file already living under ``base_dir``, grouped by byte size
    (stat-only; hashing is deferred to same-size lookups via the digest cache)."""
    result: dict[int, list[Path]] = {}
    for p in base_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.suffix.lower() in _IMAGE_EXTS:
            continue
        try:
            size = p.stat().st_size
        except OSError:
            continue
        result.setdefault(size, []).append(p)
    return result


def run_ingestion(data_dir: str | Path, chunk_size: int | None = None, chunk_overlap: int | None = None, echo_fn: callable = print):
    chunk_size = chunk_size or CHUNK_SIZE
    chunk_overlap = chunk_overlap or CHUNK_OVERLAP

    echo_fn(f"[1/4] Loading documents from {data_dir} ...")
    loader = MarkdownLoader(data_dir, echo_fn=echo_fn)
    docs = loader.load_all()

    echo_fn(f"[2/4] Splitting documents (chunk_size={chunk_size}, overlap={chunk_overlap}) ...")
    splitter = create_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(docs)
    echo_fn(f"  -> {len(chunks)} chunks created")

    echo_fn(f"[2.5/4] Loading embedding model ...")
    embeddings = get_embedding_model()

    echo_fn(f"[3/4] Building vector store ...")
    get_vector_store(embeddings)
    add_documents_with_progress(chunks, echo_fn=echo_fn)

    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import build_graph_store
        from src.graph_store.retriever import set_graph
        kg = build_graph_store()
        set_graph(kg)

    update_tracker("internal", data_dir)
    return len(chunks)


def run_incremental_update(internal_dir: str, external_dir: str, echo_fn: callable = print):
    data_dirs = [(internal_dir, "internal"), (external_dir, "external")]
    changed, unchanged = get_changed_files(data_dirs)
    if not changed:
        echo_fn("没有检测到文件变更")
        return 0

    echo_fn(f"检测到 {len(changed)} 个文件变更，{len(unchanged)} 个文件未变更")

    # 删除旧 chunks
    for p in changed:
        source_name = Path(p).name
        echo_fn(f"  删除旧数据: {source_name}")
        delete_by_source(source_name)

    all_docs = []
    source_map: dict[str, str] = {}
    for dir_path, source_type in data_dirs:
        loader = MarkdownLoader(dir_path, echo_fn=echo_fn)
        for d in loader.load_all():
            source_key = d.metadata.get("source", "")
            if source_key:
                all_docs.append(d)
                source_map.setdefault(source_key, source_type)

    changed_names = {Path(p).name for p in changed}
    changed_docs = [d for d in all_docs if Path(d.metadata.get("source", "")).name in changed_names]

    if not changed_docs:
        echo_fn("没有需要更新的文档")
        return 0

    splitter = create_splitter()
    chunks = splitter.split_documents(changed_docs)
    echo_fn(f"  -> {len(chunks)} 个新文档片段")

    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks, echo_fn=echo_fn)

    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        from src.llm import get_llm
        kg = KnowledgeGraph(echo_fn=echo_fn)
        llm = get_llm(temperature=0) if ENABLE_GRAPH_LLM_EXTRACTION else None
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    update_tracker("internal", internal_dir, changed)
    update_tracker("external", external_dir, changed)

    echo_fn(f"  -> Done! 更新了 {len(chunks)} 个片段")
    return len(chunks)


def sync_experience(echo_fn: callable = print) -> dict:
    """Incrementally index the configured experience-library directories.

    Reads the curated ``EXPERIENCE_DIRS`` in place (no copy into the data
    dir). Only new or changed ``md/txt/pdf`` files are processed, keyed by
    their full relative source path, so repeated scheduled runs never create
    duplicate chunks for modified files.

    Returns a summary dict: {dirs, changed, skipped, chunks, graph_chunks}.
    """
    from config import EXPERIENCE_DIRS
    from src.graph_store.graph import KnowledgeGraph
    from src.graph_store.retriever import set_graph

    dirs = [Path(d) for d in EXPERIENCE_DIRS if Path(d).is_dir()]
    if not dirs:
        echo_fn("EXPERIENCE_DIRS 未配置或目录不存在")
        return {"dirs": 0, "changed": 0, "skipped": 0, "chunks": 0, "graph_chunks": 0}

    data_dirs = [(str(d), "experience") for d in dirs]
    changed, unchanged = get_changed_files(data_dirs)
    echo_fn(f"经验库: {len(dirs)} 个目录 · 变更 {len(changed)} · 未变更 {len(unchanged)}")
    if not changed:
        return {"dirs": len(dirs), "changed": 0, "skipped": len(unchanged), "chunks": 0, "graph_chunks": 0}

    changed_by_source: dict[str, str] = {}
    for d in dirs:
        dabs = d.resolve()
        for p in changed:
            fp = Path(p)
            try:
                rel = str(fp.resolve().relative_to(dabs))
            except ValueError:
                continue
            if rel not in changed_by_source:
                changed_by_source[rel] = p

    all_docs = []
    for d in dirs:
        loader = MarkdownLoader(d, echo_fn=echo_fn)
        for doc in loader.load_all():
            if doc.metadata.get("source"):
                all_docs.append(doc)

    changed_docs = [doc for doc in all_docs if doc.metadata["source"] in changed_by_source]
    if not changed_docs:
        echo_fn("没有需要更新的经验文档")
        return {"dirs": len(dirs), "changed": len(changed), "skipped": len(unchanged),
                "chunks": 0, "graph_chunks": 0}

    for source in changed_by_source:
        delete_by_source(source)

    splitter = create_splitter()
    chunks = splitter.split_documents(changed_docs)
    echo_fn(f"  -> {len(chunks)} 个经验片段")

    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks, echo_fn=echo_fn)

    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.llm import get_llm
        kg = KnowledgeGraph(echo_fn=echo_fn)
        llm = get_llm(temperature=0) if ENABLE_GRAPH_LLM_EXTRACTION else None
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    for d in dirs:
        update_tracker("experience", d)

    echo_fn(f"  -> Done! 更新了 {len(chunks)} 个片段")
    return {"dirs": len(dirs), "changed": len(changed), "skipped": len(unchanged),
            "chunks": len(chunks), "graph_chunks": len(chunks)}


def run_single_file_update(filepath: str, echo_fn: callable = print):
    path = Path(filepath)
    if not path.exists():
        echo_fn(f"文件不存在: {filepath}")
        return 0

    # 先删旧 chunks，再加新 chunks
    delete_by_source(path.name)
    echo_fn(f"  删除旧数据: {path.name}")

    docs = load_path(path)
    if not docs:
        echo_fn("  -> 未加载到文档")
        return 0

    splitter = create_splitter()
    chunks = splitter.split_documents(docs)
    echo_fn(f"  -> {path.name}: {len(chunks)} 个片段")

    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks, echo_fn=echo_fn)

    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        from src.llm import get_llm
        kg = KnowledgeGraph(echo_fn=echo_fn)
        llm = get_llm(temperature=0) if ENABLE_GRAPH_LLM_EXTRACTION else None
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    update_tracker("external", path.parent, [str(path)])
    echo_fn(f"  -> Done! 更新了 {len(chunks)} 个片段")
    return len(chunks)


def run_add_path(path: str, external_dir: str = "./data/external", echo_fn: callable = print):
    from src.ingestion.loader import _iter_files
    from src.ingestion.tracker import is_already_indexed
    src = Path(path)
    if not src.exists():
        echo_fn(f"路径不存在: {path}")
        return 0

    target_base = Path(external_dir)
    target_base.mkdir(parents=True, exist_ok=True)

    copied_paths = []

    if src.is_file():
        target = target_base / src.name
        if is_already_indexed([str(src)]):
            echo_fn(f"  -> {src.name} 已添加过，跳过")
            return 0
        existing = {_file_sha256(p) for p in _existing_by_size(target_base).get(src.stat().st_size, [])}
        if _file_sha256(src) in existing:
            echo_fn(f"  -> {src.name} 与知识库已有文件内容相同，跳过")
            return 0
        if target.exists():
            stem = target.stem
            suffix = target.suffix
            counter = 1
            while target.exists():
                target = target_base / f"{stem}_{counter}{suffix}"
                counter += 1
            echo_fn(f"  同名文件已存在，重命名为: {target.name}")
        shutil.copy2(str(src), str(target))
        copied_paths.append(str(target))
        echo_fn(f"[1/3] Copying {src.name} -> {target}")

    elif src.is_dir():
        src_files = list(_iter_files(src))
        if src_files and is_already_indexed([str(p) for p in src_files]):
            echo_fn(f"  -> 目录 {src.name} 已添加过，跳过")
            return 0
        target = target_base / src.name
        by_size = _existing_by_size(target_base)
        if target.exists():
            echo_fn(f"  目标目录 {target.name} 已存在（疑似上次未完成的副本），仅补充缺失文件")
        target.mkdir(parents=True, exist_ok=True)
        digest_cache: dict[int, set[str]] = {}
        seen: set[str] = set()
        skipped = 0
        for p in src_files:
            size = p.stat().st_size
            if size not in digest_cache:
                digest_cache[size] = {_file_sha256(x) for x in by_size.get(size, [])}
            digest = _file_sha256(p)
            if digest in digest_cache[size] or digest in seen:
                skipped += 1
                continue
            rel = p.relative_to(src)
            dest = target / rel
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(str(p), str(dest))
            seen.add(digest)
            copied_paths.append(str(dest))
        echo_fn(f"[1/3] Copying directory {src.name} -> {target} ({len(copied_paths)} 新增, {skipped} 重复跳过)")
        if not copied_paths:
            echo_fn("  -> 没有新增内容（全部与知识库已有文件重复）")
            return 0

    echo_fn(f"[2/3] Loading and splitting ...")
    if src.is_dir():
        docs = load_files(copied_paths, target, echo_fn=echo_fn)
    else:
        docs = load_path(target, echo_fn=echo_fn)
    if not docs:
        echo_fn("  -> 未找到可处理的文档，已复制到外部目录")
        return 0
    echo_fn(f"  -> {len(docs)} documents loaded")

    splitter = create_splitter()
    chunks = splitter.split_documents(docs)
    echo_fn(f"  -> {len(chunks)} chunks created")

    echo_fn(f"[2.5/3] Loading embedding model (首次约需下载 33MB) ...")
    embeddings = get_embedding_model()

    echo_fn(f"[3/3] Vectorizing ...")
    get_vector_store(embeddings)
    add_documents_with_progress(chunks, echo_fn=echo_fn)

    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        from src.llm import get_llm
        kg = KnowledgeGraph(echo_fn=echo_fn)
        llm = get_llm(temperature=0) if ENABLE_GRAPH_LLM_EXTRACTION else None
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    update_tracker("external", target_base, copied_paths)
    echo_fn(f"  -> Done! 添加了 {len(chunks)} 个片段")
    return len(chunks)


def run_remove(source_name: str, external_dir: str = "./data/external", keep_file: bool = False, echo_fn: callable = print):
    delete_by_source(source_name)

    if not keep_file:
        target_base = Path(external_dir)
        for f in target_base.rglob("*"):
            if f.name == source_name:
                if f.is_file():
                    f.unlink()
                    echo_fn(f"  删除文件: {f}")
                elif f.is_dir():
                    shutil.rmtree(str(f))
                    echo_fn(f"  删除目录: {f}")

    remove_from_tracker(source_name, source_type="external")
    rebuild_bm25(get_vector_store(), echo_fn=echo_fn)
    echo_fn(f"  -> 已从知识库移除: {source_name}")



