import shutil
from pathlib import Path

from config import CHUNK_OVERLAP, CHUNK_SIZE
from src.ingestion.loader import MarkdownLoader, load_path
from src.ingestion.splitter import create_splitter
from src.ingestion.tracker import get_changed_files, update_tracker, remove_from_tracker
from src.retrieval.retriever import rebuild_bm25
from src.vector_store.chroma_client import get_vector_store, reset_vector_store, delete_by_source, add_documents_with_progress
from src.vector_store.embedding import get_embedding_model


def run_ingestion(data_dir: str | Path, chunk_size: int | None = None, chunk_overlap: int | None = None):
    chunk_size = chunk_size or CHUNK_SIZE
    chunk_overlap = chunk_overlap or CHUNK_OVERLAP

    print(f"[1/4] Loading documents from {data_dir} ...")
    loader = MarkdownLoader(data_dir)
    docs = loader.load_all()

    print(f"[2/4] Splitting documents (chunk_size={chunk_size}, overlap={chunk_overlap}) ...")
    splitter = create_splitter(chunk_size, chunk_overlap)
    chunks = splitter.split_documents(docs)
    print(f"  -> {len(chunks)} chunks created")

    print(f"[3/4] Initializing embedding model ...")
    embeddings = get_embedding_model()

    print(f"[4/4] Building vector store ...")
    get_vector_store(embeddings)
    add_documents_with_progress(chunks)

    rebuild_bm25(get_vector_store())

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import build_graph_store
        build_graph_store()

    update_tracker("internal", data_dir)
    return len(chunks)


def run_incremental_update(internal_dir: str, external_dir: str):
    data_dirs = [(internal_dir, "internal"), (external_dir, "external")]
    changed, unchanged = get_changed_files(data_dirs)
    if not changed:
        print("没有检测到文件变更")
        return 0

    print(f"检测到 {len(changed)} 个文件变更，{len(unchanged)} 个文件未变更")

    all_docs = []
    for dir_path, _ in data_dirs:
        loader = MarkdownLoader(dir_path)
        all_docs.extend(loader.load_all())

    changed_docs = [d for d in all_docs if Path(d.metadata["source"]).name in [Path(p).name for p in changed]]

    if not changed_docs:
        print("没有需要更新的文档")
        return 0

    splitter = create_splitter()
    chunks = splitter.split_documents(changed_docs)
    print(f"  -> {len(chunks)} 个新文档片段")

    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks)

    rebuild_bm25(get_vector_store())

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        kg = KnowledgeGraph()
        llm = None
        if ENABLE_GRAPH_LLM_EXTRACTION:
            from langchain_openai import ChatOpenAI
            from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
            llm = ChatOpenAI(model=LLM_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_BASE, temperature=0)
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    update_tracker("internal", internal_dir, changed)
    update_tracker("external", external_dir, changed)

    print(f"  -> Done! 更新了 {len(chunks)} 个片段")
    return len(chunks)


def run_single_file_update(filepath: str):
    path = Path(filepath)
    if not path.exists():
        print(f"文件不存在: {filepath}")
        return 0

    from src.ingestion.loader import TextLoader
    loader = TextLoader(str(path), encoding="utf-8")
    docs = loader.load()
    for doc in docs:
        doc.metadata["source"] = path.name

    splitter = create_splitter()
    chunks = splitter.split_documents(docs)
    print(f"  -> {path.name}: {len(chunks)} 个片段")

    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks)

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        kg = KnowledgeGraph()
        llm = None
        if ENABLE_GRAPH_LLM_EXTRACTION:
            from langchain_openai import ChatOpenAI
            from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
            llm = ChatOpenAI(model=LLM_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_BASE, temperature=0)
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    print(f"  -> Done! 更新了 {len(chunks)} 个片段")
    return len(chunks)


def run_add_path(path: str, external_dir: str = "./data/external"):
    src = Path(path)
    if not src.exists():
        print(f"路径不存在: {path}")
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
            print(f"  同名文件已存在，重命名为: {target.name}")
        shutil.copy2(str(src), str(target))
        copied_paths.append(str(target))
        print(f"[1/3] Copying {src.name} -> {target}")

    elif src.is_dir():
        target = target_base / src.name
        if target.exists():
            stem = target.stem
            counter = 1
            while target.exists():
                target = target_base / f"{stem}_{counter}"
                counter += 1
            print(f"  同名目录已存在，重命名为: {target.name}")
        shutil.copytree(str(src), str(target))
        copied_paths.append(str(target))
        print(f"[1/3] Copying directory {src.name} -> {target}")

    print(f"[2/3] Loading and splitting ...")
    docs = load_path(target)
    if not docs:
        print("  未找到可处理的文档")
        return 0
    print(f"  -> {len(docs)} documents loaded")

    splitter = create_splitter()
    chunks = splitter.split_documents(docs)
    print(f"  -> {len(chunks)} chunks created")

    print(f"[3/3] Vectorizing ...")
    embeddings = get_embedding_model()
    get_vector_store(embeddings)
    add_documents_with_progress(chunks)

    rebuild_bm25(get_vector_store())

    from config import ENABLE_GRAPH, ENABLE_GRAPH_LLM_EXTRACTION
    if ENABLE_GRAPH:
        from src.graph_store.graph import KnowledgeGraph
        from src.graph_store.retriever import set_graph
        kg = KnowledgeGraph()
        llm = None
        if ENABLE_GRAPH_LLM_EXTRACTION:
            from langchain_openai import ChatOpenAI
            from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
            llm = ChatOpenAI(model=LLM_MODEL, api_key=DEEPSEEK_API_KEY, base_url=DEEPSEEK_API_BASE, temperature=0)
        kg.add_chunks(chunks, llm=llm)
        kg.save()
        set_graph(kg)

    update_tracker("external", target_base, copied_paths)
    print(f"  -> Done! 添加了 {len(chunks)} 个片段")
    return len(chunks)


def run_remove(source_name: str, external_dir: str = "./data/external"):
    delete_by_source(source_name)

    target_base = Path(external_dir)
    for f in target_base.rglob("*"):
        if f.name == source_name or f.name == source_name:
            if f.is_file():
                f.unlink()
                print(f"  删除文件: {f}")
            elif f.is_dir():
                shutil.rmtree(str(f))
                print(f"  删除目录: {f}")

    remove_from_tracker(source_name)
    print(f"  -> 已从知识库移除: {source_name}")



