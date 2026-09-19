from src.application.conversation_store import ConversationStore


class _Lock:
    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


def test_conversation_store_forwards_persistence_operations():
    saved = {}
    store = ConversationStore(
        allocate=lambda: "s1",
        load=lambda session_id: saved.get(session_id),
        save=lambda messages, session_id: (saved.__setitem__(session_id, messages) or session_id),
        lock=lambda _: _Lock(),
    )
    assert store.allocate() == "s1"
    with store.lock("s1"):
        assert store.load("s1") is None
        assert store.save([{"role": "user", "content": "hi"}], "s1") == "s1"
    assert store.load("s1") == [{"role": "user", "content": "hi"}]
