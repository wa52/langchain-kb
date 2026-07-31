import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar

from langchain_chroma import Chroma

from config import CHROMA_PERSIST_DIR, GRAPH_PERSIST_DIR, TOP_K, ENABLE_HYBRID_SEARCH, PRODUCT_NAME_EN

logger = logging.getLogger(__name__)


class ResourceManager:
    _instance: ClassVar['ResourceManager | None'] = None
    _lock: ClassVar[Lock] = Lock()

    def __init__(self):
        self.embedding_model: Any = None
        self.vector_store: Chroma | None = None
        self.llm: Any = None
        self.graph: Any = None
        self._initialized: bool = False
        self._shutdown_event = asyncio.Event()
        self._background_tasks: set[asyncio.Task] = set()
        self._index_version: int = 0
        self._ensemble_retriever: Any = None
        self._cached_k: int | None = None

    @classmethod
    def get_instance(cls) -> 'ResourceManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def startup(self, echo_fn=print):
        if self._initialized:
            logger.warning("ResourceManager already initialized, skipping")
            return

        echo_fn("[ResourceManager] Starting resource manager...")

        echo_fn("  [1/5] Loading embedding model ...")
        from src.vector_store.embedding import get_embedding_model
        self.embedding_model = get_embedding_model()
        echo_fn(f"  [1/5] Embedding model loaded: {type(self.embedding_model).__name__}")

        echo_fn("  [2/5] Initializing LLM client ...")
        from src.llm import get_llm
        self.llm = get_llm(temperature=0)
        echo_fn(f"  [2/5] LLM client initialized")

        echo_fn("  [3/5] Connecting to vector store ...")
        self.vector_store = Chroma(
            collection_name="langchain_docs",
            persist_directory=CHROMA_PERSIST_DIR,
            embedding_function=self.embedding_model,
        )
        echo_fn(f"  [3/5] Vector store connected: {CHROMA_PERSIST_DIR}")

        echo_fn("  [4/5] Loading knowledge graph ...")
        from src.graph_store.graph import KnowledgeGraph
        self.graph = KnowledgeGraph()
        nc = self.graph.graph.number_of_nodes()
        ec = self.graph.graph.number_of_edges()
        echo_fn(f"  [4/5] Knowledge graph loaded: {nc} entities, {ec} relations")

        echo_fn("  [5/5] Building BM25 index ...")
        self._rebuild_bm25(echo_fn=echo_fn)
        echo_fn("  [5/5] BM25 index ready")

        self._initialize_existing_singletons()

        self._initialized = True
        echo_fn("[ResourceManager] Startup complete")

    def shutdown(self, echo_fn=print):
        echo_fn("[ResourceManager] Shutting down...")
        self._shutdown_event.set()

        if self._background_tasks:
            echo_fn(f"  Waiting for {len(self._background_tasks)} background tasks to finish...")

        self._ensemble_retriever = None
        self._cached_k = None
        self.embedding_model = None
        self.vector_store = None
        self.llm = None
        self.graph = None
        self._initialized = False
        echo_fn("[ResourceManager] Shutdown complete")

    def is_ready(self) -> bool:
        return self._initialized

    def get_retriever(self, k: int | None = None):
        if not self._initialized:
            raise RuntimeError("ResourceManager not initialized. Call startup() first.")
        from langchain_classic.retrievers.ensemble import EnsembleRetriever
        k = k or TOP_K

        if self._ensemble_retriever is not None and self._cached_k == k:
            return self._ensemble_retriever

        vector_retriever = self.vector_store.as_retriever(
            search_type="mmr",
            search_kwargs={"k": k, "fetch_k": k * 4},
        )

        from src.retrieval.retriever import _bm25_retriever
        if ENABLE_HYBRID_SEARCH and _bm25_retriever is not None:
            self._ensemble_retriever = EnsembleRetriever(
                retrievers=[vector_retriever, _bm25_retriever],
                weights=[0.5, 0.5],
            )
        else:
            self._ensemble_retriever = vector_retriever
        self._cached_k = k
        return self._ensemble_retriever

    def invalidate_retriever_cache(self):
        self._ensemble_retriever = None
        self._cached_k = None
        self._index_version += 1

    def get_index_version(self) -> int:
        return self._index_version

    def start_background_task(self, coro, name: str = "unnamed"):
        task = asyncio.create_task(coro, name=name)
        self._background_tasks.add(task)
        task.add_done_callback(self._background_tasks.discard)
        logger.info(f"Background task started: {name}")

    def _rebuild_bm25(self, echo_fn=print):
        from src.retrieval.retriever import rebuild_bm25
        rebuild_bm25(self.vector_store, echo_fn=echo_fn)

    def _initialize_existing_singletons(self):
        from src.vector_store.chroma_client import set_vector_store
        set_vector_store(self.vector_store)
        if self.graph is not None:
            from src.graph_store.retriever import set_graph
            set_graph(self.graph)


@asynccontextmanager
async def app_lifespan(app):
    logger.info("=" * 50)
    logger.info(f"  {PRODUCT_NAME_EN} API starting...")
    logger.info("=" * 50)
    rm = ResourceManager.get_instance()
    rm.startup(echo_fn=logger.info)
    if rm.embedding_model:
        logger.info(f"  Embedding model:  {type(rm.embedding_model).__name__}")
    if rm.llm:
        logger.info(f"  LLM client:       initialized")
    if rm.vector_store:
        logger.info(f"  Vector store:     connected")
    if rm.graph:
        logger.info(f"  Knowledge graph:  {rm.graph.graph.number_of_nodes()} entities")
    logger.info(f"  Index version:    {rm.get_index_version()}")
    logger.info("=" * 50)
    try:
        yield
    finally:
        logger.info("=" * 50)
        logger.info("  Server shutting down - releasing resources")
        logger.info("=" * 50)
        rm.shutdown(echo_fn=logger.info)
