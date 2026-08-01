import shutil
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE
from src.ingestion.loader import MarkdownLoader, load_path
from src.ingestion.splitter import create_splitter
from src.ingestion.tracker import get_changed_files, update_tracker, remove_from_tracker
from src.retrieval.retriever import rebuild_bm25
from src.vector_store.chroma_client import get_vector_store, reset_vector_store, delete_by_source, add_documents_with_progress
from src.vector_store.embedding import get_embedding_model

_IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".gif", ".jp2", ".webp"}


def _ignore_images(directory, names):
    """shutil.copytree ignore filter: drop image files while copying, so the
    external data dir only holds indexable content."""
    return [n for n in names if (Path(directory) / n).suffix.lower() in _IMAGE_EXTS]


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
    src = Path(path)
    if not src.exists():
        echo_fn(f"路径不存在: {path}")
        return 0

    target_base = Path(external_dir)
    target_base.mkdir(parents=True, exist_ok=True)

    copied_paths = []

    if src.is_file():
        target = target_base / src.name
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
        target = target_base / src.name
        if target.exists():
            stem = target.stem
            counter = 1
            while target.exists():
                target = target_base / f"{stem}_{counter}"
                counter += 1
            echo_fn(f"  同名目录已存在，重命名为: {target.name}")
        echo_fn("  正在复制目录到 data/external/ ...")
        shutil.copytree(str(src), str(target), ignore=_ignore_images)
        copied_paths.append(str(target))
        echo_fn(f"[1/3] Copying directory {src.name} -> {target}")

    echo_fn(f"[2/3] Loading and splitting ...")
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



