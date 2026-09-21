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

    assert engine.answer([{"role": "user", "content": "explain RAG", "route": "direct"}]) == "direct answer"
    assert llm.messages == [
        {"role": "system", "content": "system"},
        {"role": "user", "content": "explain RAG"},
    ]
    assert list(engine.stream([{"role": "user", "content": "explain RAG"}])) == ["a", "b"]


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


def test_direct_engine_answers_pure_greeting_without_calling_the_model():
    class NoModel:
        def invoke(self, _messages):
            raise AssertionError("a pure greeting must not call the model")

        def stream(self, _messages):
            raise AssertionError("a pure greeting must not stream from the model")

    engine = DirectChatEngine(lambda: NoModel(), "system", len, 100)
    messages = [{"role": "user", "content": "你好！"}]

    assert engine.answer(messages) == "你好，请直接发送问题。"
    assert list(engine.stream(messages)) == ["你好，请直接发送问题。"]
