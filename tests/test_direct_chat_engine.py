from src.application.direct_chat import DirectChatEngine


class _Response:
    content = " direct answer "


class _LLM:
    def invoke(self, messages):
        self.messages = messages
        return _Response()

    def stream(self, messages):
        self.messages = messages
        return iter(["a", type("Chunk", (), {"content": "b"})()])


def test_direct_engine_normalizes_and_invokes_model():
    llm = _LLM()
    engine = DirectChatEngine(lambda: llm, "system", lambda text: len(text), 100)

    assert engine.answer([{"role": "user", "content": "hi", "route": "direct"}]) == "direct answer"
    assert llm.messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "hi"},
    ]
    assert list(engine.stream([{"role": "user", "content": "hi"}])) == ["a", "b"]


def test_direct_engine_trims_oldest_pairs_within_budget():
    engine = DirectChatEngine(lambda: _LLM(), "system", lambda text: len(text), 2)

    messages = [
        {"role": "user", "content": "old"},
        {"role": "assistant", "content": "reply"},
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "new"},
    ]
    assert engine.trim_history(messages) == [
        {"role": "user", "content": "older"},
        {"role": "assistant", "content": "reply2"},
        {"role": "user", "content": "new"},
    ]
