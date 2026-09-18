from unittest.mock import patch


def test_worker_pid_is_registered_and_removed(tmp_path, monkeypatch):
    from src.bootstrap.lifecycle import _register_worker_pid, _remove_worker_pid

    path = tmp_path / "worker.pid"
    monkeypatch.setenv("KNOWLEDGE_WORKER_PID_FILE", str(path))
    with patch("src.bootstrap.lifecycle.os.getpid", return_value=9876):
        registered = _register_worker_pid()
        assert registered == path
        assert path.read_text(encoding="ascii") == "9876"
        _remove_worker_pid(path)
    assert not path.exists()
