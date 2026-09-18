"""Provider-neutral language-model port."""

from collections.abc import Iterable
from typing import Protocol


class LLM(Protocol):
    def invoke(self, messages: list[dict[str, str]]) -> str: ...

    def stream(self, messages: list[dict[str, str]]) -> Iterable[str]: ...
