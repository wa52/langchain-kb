"""Framework-independent knowledge-base value objects."""

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Query:
    text: str
    limit: int = 5
    capability: str | None = None

    def __post_init__(self) -> None:
        if not self.text.strip():
            raise ValueError("query text must not be empty")
        if self.limit < 1:
            raise ValueError("query limit must be positive")


@dataclass(frozen=True)
class DocumentChunk:
    content: str
    source: str = ""
    chunk_id: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RetrievalResult:
    chunk: DocumentChunk
    score: float | None = None
    rank: int = 0
    channel: str = "vector"
