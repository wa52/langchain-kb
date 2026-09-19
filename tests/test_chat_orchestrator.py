from src.application.chat_orchestrator import ChatOrchestrator


class _Backend:
    def __init__(self):
        self.calls = []

    def answer(self, query, session_id=None):
        self.calls.append(("answer", query, session_id))
        return "ok", session_id or "s1", 1.0

    def stream(self, query, session_id, stop_event):
        self.calls.append(("stream", query, session_id, stop_event))
        return iter([{"type": "message_end"}])

    def resume(self, session_id, decision, message, stop_event, decisions=None):
        self.calls.append(("resume", session_id, decision, message, stop_event, decisions))
        return iter([{"type": "message_end"}])


def test_orchestrator_injects_and_reuses_backend():
    backend = _Backend()
    calls = []
    orchestrator = ChatOrchestrator(lambda: calls.append(True) or backend)

    assert orchestrator.answer("hello", "s1") == ("ok", "s1", 1.0)
    assert list(orchestrator.stream("next", "s1", None)) == [{"type": "message_end"}]
    assert len(calls) == 1
    assert backend.calls[0] == ("answer", "hello", "s1")


def test_orchestrator_forwards_resume_options():
    backend = _Backend()
    orchestrator = ChatOrchestrator(lambda: backend)

    list(orchestrator.resume("s1", "approve", "go", None, decisions=["approve"]))

    assert backend.calls == [("resume", "s1", "approve", "go", None, ["approve"])]
