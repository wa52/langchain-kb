"""Provider-agnostic direct (non-RAG) chat engine."""

from collections.abc import Callable, Iterable
from typing import Any


class DirectChatEngine:
    """Execute a short-context LLM conversation without retrieval tools."""

    def __init__(
        self,
        llm_factory: Callable[[], Any],
        system_prompt: str,
        token_estimator: Callable[[str], int],
        max_tokens: int,
    ) -> None:
        self._llm_factory = llm_factory
        self._system_prompt = system_prompt
        self._token_estimator = token_estimator
        self._max_tokens = max_tokens

    @staticmethod
    def model_messages(messages: list[dict]) -> list[dict]:
        """Remove service metadata before sending messages to a model."""
        return [
            {"role": message.get("role", ""), "content": message.get("content", "")}
            for message in messages
        ]

    def prompt_messages(self, messages: list[dict]) -> list[dict]:
        return [
            {"role": "system", "content": self._system_prompt},
            *self.model_messages(messages),
        ]

    def trim_history(self, messages: list[dict]) -> list[dict]:
        if len(messages) < 2:
            return messages
        history = list(messages[:-1])
        current = messages[-1]
        while len(history) > 2 and sum(
            self._token_estimator(str(message.get("content", ""))) for message in history
        ) > self._max_tokens:
            history = history[2:]
        return history + [current]

    def answer(self, messages: list[dict]) -> str:
        response = self._llm_factory().invoke(self.prompt_messages(messages))
        content = getattr(response, "content", response)
        return str(content or "").strip()

    def stream(self, messages: list[dict]) -> Iterable[str]:
        for chunk in self._llm_factory().stream(self.prompt_messages(messages)):
            content = getattr(chunk, "content", chunk)
            if content:
                yield str(content)
