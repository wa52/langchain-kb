from types import SimpleNamespace

import pytest


def _request(name):
    return SimpleNamespace(tool_call={"name": name})


def test_read_only_tool_retries_once():
    from src.agent.harness import ToolRecoveryMiddleware

    calls = []

    def handler(_request):
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("temporary")
        return "ok"

    assert ToolRecoveryMiddleware().wrap_tool_call(_request("read_file"), handler) == "ok"
    assert len(calls) == 2


def test_write_tool_is_not_retried():
    from src.agent.harness import ToolRecoveryMiddleware

    calls = []

    def handler(_request):
        calls.append(1)
        raise RuntimeError("failed")

    with pytest.raises(RuntimeError):
        ToolRecoveryMiddleware().wrap_tool_call(_request("write_file"), handler)
    assert len(calls) == 1


def test_verify_agent_run_reports_tool_errors_and_empty_answers():
    from src.agent.harness import verify_agent_run

    assert verify_agent_run("answer", [], False)["complete"] is True
    assert verify_agent_run("answer", [{"status": "error"}], False)["reason"] == "tool_error"
    assert verify_agent_run("", [], False)["reason"] == "empty_answer"
    assert verify_agent_run("", [], True)["reason"] == "waiting_approval"
