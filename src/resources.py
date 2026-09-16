import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from threading import Lock
from typing import Any, ClassVar

from langchain_chroma import Chroma

import config
from config import CHROMA_PERSIST_DIR, GRAPH_PERSIST_DIR, TOP_K, ENABLE_HYBRID_SEARCH, PRODUCT_NAME_EN, EMBEDDING_MODEL
from src.status import get_registry

logger = logging.getLogger(__name__)


class ResourceManager:
    _instance: ClassVar['ResourceManager | None'] = None
    _lock: ClassVar[Lock] = Lock()

    def __init__(self):
        self.embedding_model: Any = None
        self.vector_store: Chroma | None = None
        self.llm: Any = None
        self.graph: Any = None
        self.agent: Any = None
        self._initialized: bool = False
        self._shutdown_event = asyncio.Event()
        self._background_tasks: set[asyncio.Task] = set()
        self._index_version: int = 0
        self._ensemble_retriever: Any = None
        self._cached_k: int | None = None
        # Guards lazy agent construction; separate from _lock (which guards
        # singleton creation) so a long agent build never blocks get_instance().
        self._agent_lock = Lock()

    @classmethod
    def get_instance(cls) -> 'ResourceManager':
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance

    def startup(self, echo_fn=print):
        import time
        if self._initialized:
            logger.warning("ResourceManager already initialized, skipping")
            return
        self._shutdown_event.clear()

        t_start = time.time()
        echo_fn("[ResourceManager] Starting resource manager...")

        def _step(name):
            t = time.time()
            echo_fn(f"  [{name}] {t - t_start:.2f}s")
            return t

        try:
            reg = get_registry()

            echo_fn("  [1/5] Loading embedding model ...")
            reg.set_loading("embedding", EMBEDDING_MODEL)
            t_step = time.time()
            from src.vector_store.embedding import get_embedding_model
            self.embedding_model = get_embedding_model()
            reg.set_ready("embedding", type(self.embedding_model).__name__)
            echo_fn(f"  [1/5] Embedding model loaded: {type(self.embedding_model).__name__} ({time.time() - t_step:.2f}s)")

            echo_fn("  [2/5] Initializing LLM client ...")
            reg.set_loading("llm", "初始化 LLM 客户端")
            t_step = time.time()
            from src.llm import get_llm
            self.llm = get_llm(temperature=0)
            reg.set_ready("llm", "DeepSeek/OpenAI 兼容")
            echo_fn(f"  [2/5] LLM client initialized ({time.time() - t_step:.2f}s)")

            echo_fn("  [3/5] Connecting to vector store ...")
            reg.set_loading("vector_store", CHROMA_PERSIST_DIR)
            t_step = time.time()
            self.vector_store = Chroma(
                collection_name="langchain_docs",
                persist_directory=CHROMA_PERSIST_DIR,
                embedding_function=self.embedding_model,
            )
            reg.set_ready("vector_store", CHROMA_PERSIST_DIR)
            echo_fn(f"  [3/5] Vector store connected: {CHROMA_PERSIST_DIR} ({time.time() - t_step:.2f}s)")

            echo_fn("  [4/5] Loading knowledge graph ...")
            reg.set_loading("graph", "加载知识图谱")
            t_step = time.time()
            from src.graph_store.graph import KnowledgeGraph
            self.graph = KnowledgeGraph()
            nc = self.graph.graph.number_of_nodes()
            ec = self.graph.graph.number_of_edges()
            reg.set_ready("graph", f"{nc} entities, {ec} relations")
            echo_fn(f"  [4/5] Knowledge graph loaded: {nc} entities, {ec} relations ({time.time() - t_step:.2f}s)")

            echo_fn("  [5/5] Building BM25 index ...")
            reg.set_loading("bm25", "加载/构建 BM25 索引")
            t_step = time.time()
            self._rebuild_bm25(echo_fn=echo_fn)
            echo_fn(f"  [5/5] BM25 index ready ({time.time() - t_step:.2f}s)")

            self._initialize_existing_singletons()

            self._initialized = True
            echo_fn(f"[ResourceManager] Startup complete (total {time.time() - t_start:.2f}s)")
        except Exception:
            # Roll back partially-initialized state so a later startup retry
            # does not inherit stale resources. Mark still-loading components
            # as failed for the monitoring layer.
            for name, c in get_registry().snapshot().items():
                if c["state"] == "loading":
                    get_registry().set_error(name, "startup aborted")
            self.embedding_model = None
            self.llm = None
            self.vector_store = None
            self.graph = None
            self.agent = None
            self._initialized = False
            raise

    def shutdown(self, echo_fn=print):
        echo_fn("[ResourceManager] Shutting down...")
        self._shutdown_event.set()

        if self._background_tasks:
            echo_fn(f"  Cancelling {len(self._background_tasks)} background tasks...")
            for task in self._background_tasks:
                task.cancel()
            self._background_tasks.clear()

        self._ensemble_retriever = None
        self._cached_k = None
        self.embedding_model = None
        self.vector_store = None
        self.llm = None
        self.graph = None
        self.agent = None
        self._initialized = False
        from src.status import reset_status
        reset_status()
        echo_fn("[ResourceManager] Shutdown complete")

    def is_ready(self) -> bool:
        return self._initialized

    def get_agent(self):
        """Return the cached RAG agent, building it lazily on first call.
        The agent is stateless (messages are passed per-call), so it is safe
        to reuse across chat requests. Double-checked locking prevents
        concurrent first calls from building duplicate agents."""
        if self.agent is not None:
            return self.agent
        with self._agent_lock:
            if self.agent is not None:
                return self.agent
            if not self._initialized:
                raise RuntimeError("ResourceManager not initialized. Call startup() first.")
            import time as _t
            t0 = _t.time()
            from src.agent.rag_agent import create_rag_agent
            reg = get_registry()
            reg.set_loading("agent", "构建 RAG Agent")
            try:
                self.agent = create_rag_agent()
            except Exception as e:
                reg.set_error("agent", e, "构建 RAG Agent")
                raise
            reg.set_ready("agent", "Deep Agent")
            print(f"  [计时] 首次构建 RAG Agent（缓存复用）: {_t.time() - t0:.2f}s")
            return self.agent

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
    from src.api.services import sync as sync_service
    # Keep one lightweight scheduler alive even when no directory is configured
    # yet, so adding the first sync directory at runtime takes effect.
    rm.start_background_task(sync_service.sync_loop(), name="scheduled-experience-sync")
    try:
        yield
    finally:
        logger.info("=" * 50)
        logger.info("  Server shutting down - releasing resources")
        logger.info("=" * 50)
        rm.shutdown(echo_fn=logger.info)
