"""Compatibility adapter for the current JSON session store."""


def list_sessions() -> list[dict]:
    from src.agent.chat_history import list_sessions as _list
    return _list()


def load_history(session_id: str):
    from src.agent.chat_history import load_history as _load
    return _load(session_id)


def delete_history(session_id: str) -> bool:
    from src.agent.chat_history import delete_history as _delete
    return _delete(session_id)
