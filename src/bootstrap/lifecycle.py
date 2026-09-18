"""Process-lifecycle adapter for the knowledge-base application.

This is the single seam between an ASGI server lifecycle and the resource
runtime.  Keeping it outside ``src.resources`` prevents storage/agent setup
from becoming coupled to FastAPI or any future transport.
"""

import asyncio
import logging
from contextlib import asynccontextmanager

import config
from config import PRODUCT_NAME_EN
from src.bootstrap.plugins import ResourceManagerPlugin
from src.harness import HarnessRuntime
from src.resources import ResourceManager

logger = logging.getLogger(__name__)


@asynccontextmanager
async def app_lifespan(app):
    """Start and stop the shared runtime for an ASGI application.

    The public interface is deliberately small: a server only supplies its
    lifecycle; resource loading, background work, cancellation and cleanup
    stay behind this module.
    """
    logger.info("=" * 50)
    logger.info("  %s API starting...", PRODUCT_NAME_EN)
    logger.info("=" * 50)
    runtime = ResourceManager.get_instance()
    harness = HarnessRuntime()
    harness.register(ResourceManagerPlugin(runtime, echo_fn=logger.info))
    app.state.harness = harness
    if config.FAST_STARTUP:
        logger.info("  FAST_STARTUP enabled; warming resources in background")
        await harness.start(background=True)
    else:
        try:
            await harness.start()
        except asyncio.CancelledError:
            await harness.stop()
            raise

    _log_runtime_state(runtime)
    from src.api.services import sync as sync_service
    if config.FAST_STARTUP:
        runtime.start_background_task(
            runtime._warmup_then_sync(sync_service.sync_loop),
            name="resource-warmup-and-scheduled-sync",
        )
    else:
        runtime.start_background_task(sync_service.sync_loop(), name="scheduled-experience-sync")
    try:
        yield
    finally:
        logger.info("=" * 50)
        logger.info("  Server shutting down - releasing resources")
        logger.info("=" * 50)
        await harness.stop()


def _log_runtime_state(runtime: ResourceManager) -> None:
    """Log an observability snapshot without exposing implementation details."""
    if runtime.embedding_model:
        logger.info("  Embedding model:  %s", type(runtime.embedding_model).__name__)
    if runtime.llm:
        logger.info("  LLM client:       initialized")
    if runtime.vector_store:
        logger.info("  Vector store:     connected")
    if runtime.graph:
        logger.info("  Knowledge graph:  %s entities", runtime.graph.graph.number_of_nodes())
    logger.info("  Index version:    %s", runtime.get_index_version())
    logger.info("=" * 50)
