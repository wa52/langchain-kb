"""Stable business vocabulary. Domain modules must not import frameworks."""

from src.domain.models import DocumentChunk, Query, RetrievalResult

__all__ = ["DocumentChunk", "Query", "RetrievalResult"]
