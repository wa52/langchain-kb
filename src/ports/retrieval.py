"""Retrieval ports. No Chroma, LangChain, or LlamaIndex types cross this seam."""

from typing import Protocol

from src.domain.models import Query, RetrievalResult


class Retriever(Protocol):
    def retrieve(self, query: Query) -> list[RetrievalResult]:
        """Return ranked chunks; adapters own the retrieval implementation."""
