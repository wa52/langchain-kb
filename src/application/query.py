"""Application retrieval use case.

The service knows the business request/response vocabulary only. Chroma,
BM25, LlamaIndex, or another engine is supplied through ``Retriever``.
"""

from src.domain.models import Query, RetrievalResult
from src.ports.retrieval import Retriever


class QueryService:
    def __init__(self, retriever: Retriever) -> None:
        self._retriever = retriever

    def search(self, text: str, *, limit: int = 5, capability: str | None = None) -> list[RetrievalResult]:
        return self._retriever.retrieve(Query(text, limit, capability))
