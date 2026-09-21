"""Provider-agnostic direct (non-RAG) chat engine."""

from collections.abc import Callable, Iterable
import re
from typing import Any


_GREETING = re.compile(
    r"^(?:你好|您好|嗨|hello|hi|早上好|下午好|晚上好)[！!。,.，\s]*$",
    re.IGNORECASE,
)
_GREETING_REPLY = "你好，请直接发送问题。"


def is_pure_greeting(text: str) -> bool:
    """Whether a message has a deterministic reply and needs no routing."""
    return bool(_GREETING.fullmatch((text or "").strip()))


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

    @staticmethod
    def _fixed_reply(messages: list[dict]) -> str | None:
        """Answer a pure greeting locally; no model call or welcome push."""
        if not messages:
            return None
        text = str(messages[-1].get("content", "")).strip()
        return _GREETING_REPLY if is_pure_greeting(text) else None

    def answer(self, messages: list[dict]) -> str:
        fixed = self._fixed_reply(messages)
        if fixed is not None:
            return fixed
        response = self._llm_factory().invoke(self.prompt_messages(messages))
        content = getattr(response, "content", response)
        return str(content or "").strip()

    def stream(self, messages: list[dict]) -> Iterable[str]:
        fixed = self._fixed_reply(messages)
        if fixed is not None:
            yield fixed
            return
        for chunk in self._llm_factory().stream(self.prompt_messages(messages)):
            content = getattr(chunk, "content", chunk)
            if content:
                yield str(content)
