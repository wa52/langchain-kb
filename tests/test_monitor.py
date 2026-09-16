"""监控测试修复程序（src/monitor.py）与项目自检入口（selfcheck.py）测试。"""

import json
import pickle
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.monitor import run_checks


def _ok(name, detail="ok"):
    return {"name": name, "ok": True, "status": "ready", "detail": detail,
            "error": None, "duration_ms": 10.0, "fix": "", "repairable": False}


def _fail(name, error="fail", repairable=False):
    return {"name": name, "ok": False, "status": "error", "detail": "err",
            "error": error, "duration_ms": 10.0, "fix": "fix", "repairable": repairable}


@pytest.fixture(autouse=True)
def reset_registry():
    from src.resources import ResourceManager
    from src.status import reset_status
    ResourceManager._instance = None
    ResourceManager._lock = type(ResourceManager._lock)()
    reset_status()
    yield
    ResourceManager._instance = None
    reset_status()


class TestRegistryCheck:

    def test_ok_when_no_stuck_loading(self):
        from src.monitor import _check_registry
        r = _check_registry()
        assert r["ok"] is True

    def test_fail_when_loading_stuck(self):
        from src.monitor import _check_registry
        from src.status import get_registry
        reg = get_registry()
        reg.set_loading("bm25", "stuck")
        reg._components["bm25"]["started_at"] = time.time() - 1000
        r = _check_registry()
        assert r["ok"] is False
        assert "bm25" in r["detail"]
        assert r["repairable"] is True


class TestDataDirsCheck:

    def test_ok_when_dirs_exist(self, tmp_path):
        from src import monitor
        (tmp_path / "docs").mkdir()
        (tmp_path / "external").mkdir()
        (tmp_path / "chroma").mkdir()
        with (
            patch.object(monitor, "DATA_DIR", tmp_path / "docs"),
            patch.object(monitor, "EXTERNAL_DIR", tmp_path / "external"),
            patch.object(monitor, "CHROMA_PERSIST_DIR", tmp_path / "chroma"),
        ):
            from src.monitor import _check_data_dirs
            assert _check_data_dirs()["ok"] is True

    def test_fail_when_dir_missing(self, tmp_path):
        from src import monitor
        with (
            patch.object(monitor, "DATA_DIR", tmp_path / "nope"),
            patch.object(monitor, "EXTERNAL_DIR", tmp_path / "external"),
            patch.object(monitor, "CHROMA_PERSIST_DIR", tmp_path / "chroma"),
        ):
            from src.monitor import _check_data_dirs
            r = _check_data_dirs()
            assert r["ok"] is False
            assert r["repairable"] is True


class TestComponentChecks:

    def test_embedding_ok(self):
        with patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()):
            from src.monitor import _check_embedding
            assert _check_embedding()["ok"] is True

    def test_llm_missing_key(self):
        from src import monitor
        with patch.object(monitor, "DEEPSEEK_API_KEY", ""):
            from src.monitor import _check_llm
            r = _check_llm()
            assert r["ok"] is False
            assert r["repairable"] is False

    def test_vector_store_ok(self):
        vs = MagicMock()
        vs._collection.count.return_value = 42
        with patch("src.vector_store.chroma_client.get_vector_store", return_value=vs):
            from src.monitor import _check_vector_store
            r = _check_vector_store()
            assert r["ok"] is True
            assert "42" in r["detail"]

    def test_bm25_in_memory_ok(self):
        bm25 = MagicMock()
        bm25.docs = [1, 2, 3]
        with patch("src.retrieval.retriever._bm25_retriever", bm25):
            from src.monitor import _check_bm25
            r = _check_bm25()
            assert r["ok"] is True
            assert "已在内存" in r["detail"]

    def test_bm25_cache_missing(self):
        with (
            patch("src.retrieval.retriever._bm25_retriever", None),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH", Path("no/such/path.pkl")),
        ):
            from src.monitor import _check_bm25
            r = _check_bm25()
            assert r["ok"] is False
            assert r["repairable"] is True

    def test_bm25_cache_stale(self, tmp_path):
        pkl = tmp_path / "bm25.pkl"
        with open(pkl, "wb") as f:
            pickle.dump({"texts": ["a", "b"]}, f)
        vs = MagicMock()
        vs._collection.count.return_value = 99
        with (
            patch("src.retrieval.retriever._bm25_retriever", None),
            patch("src.retrieval.retriever._BM25_PERSIST_PATH", pkl),
            patch("src.vector_store.chroma_client.get_vector_store", return_value=vs),
        ):
            from src.monitor import _check_bm25
            r = _check_bm25()
            assert r["ok"] is False
            assert "失效" in r["detail"]

    def test_graph_missing(self, tmp_path):
        from src import monitor
        with patch.object(monitor, "GRAPH_PERSIST_DIR", tmp_path):
            from src.monitor import _check_graph
            r = _check_graph()
            assert r["ok"] is False
            assert r["repairable"] is True

    def test_graph_ok(self, tmp_path):
        from src import monitor
        graph_path = tmp_path / "knowledge_graph.json"
        graph_path.write_text("{}", encoding="utf-8")
        kg = MagicMock()
        kg.graph.number_of_nodes.return_value = 5
        with (
            patch.object(monitor, "GRAPH_PERSIST_DIR", tmp_path),
            patch("src.graph_store.retriever.get_graph", return_value=kg),
        ):
            from src.monitor import _check_graph
            r = _check_graph()
            assert r["ok"] is True
            assert "5" in r["detail"]

    def test_agent_lazy_is_ok(self):
        from src.monitor import _check_agent
        assert _check_agent()["ok"] is True

    def test_agent_error(self):
        from src.status import get_registry
        get_registry().set_error("agent", RuntimeError("build failed"))
        from src.monitor import _check_agent
        r = _check_agent()
        assert r["ok"] is False
        assert r["repairable"] is True

    def test_index_stuck(self):
        from datetime import datetime, timedelta, timezone
        mgr = MagicMock()
        stuck = {
            "t1": {"task_id": "t1", "status": "running",
                   "created_at": (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat()},
        }
        mgr._tasks = stuck
        with patch("src.api.services.indexing.get_task_manager", return_value=mgr):
            from src.monitor import _check_index
            r = _check_index()
            assert r["ok"] is False
            assert r["repairable"] is True

    def test_tmp_files_found(self, tmp_path):
        from src import monitor
        (tmp_path / "bm25.pkl.tmp").write_bytes(b"x")
        with (
            patch.object(monitor, "CHROMA_PERSIST_DIR", tmp_path),
            patch.object(monitor, "GRAPH_PERSIST_DIR", tmp_path),
        ):
            from src.monitor import _check_tmp_files
            r = _check_tmp_files()
            assert r["ok"] is False
            assert r["repairable"] is True


class TestRepair:

    def test_repair_bm25_rebuilds(self):
        vs = MagicMock()
        with (
            patch("src.vector_store.chroma_client.get_vector_store", return_value=vs),
            patch("src.retrieval.retriever.rebuild_bm25") as mock_rebuild,
        ):
            from src.monitor import _repair_bm25
            assert _repair_bm25(echo_fn=lambda _m: None) is True
            mock_rebuild.assert_called_once()

    def test_repair_llm_not_automatable(self):
        from src.monitor import _repair_llm
        assert _repair_llm(echo_fn=lambda _m: None) is False

    def test_repair_registry_unsticks(self):
        from src.status import get_registry, snapshot_status
        from src.monitor import _repair_registry
        reg = get_registry()
        reg.set_loading("graph", "stuck")
        reg._components["graph"]["started_at"] = time.time() - 1000
        assert _repair_registry(echo_fn=lambda _m: None) is True
        assert snapshot_status()["graph"]["state"] == "ready"

    def test_repair_tmp_files_removes(self, tmp_path):
        from src import monitor
        leftover = tmp_path / "bm25.pkl.tmp"
        leftover.write_bytes(b"x")
        with (
            patch.object(monitor, "CHROMA_PERSIST_DIR", tmp_path),
            patch.object(monitor, "GRAPH_PERSIST_DIR", tmp_path),
        ):
            from src.monitor import _repair_tmp_files
            assert _repair_tmp_files(echo_fn=lambda _m: None) is True
        assert not leftover.exists()

    def test_run_repairs(self):
        from src.monitor import run_repairs
        with patch("src.monitor.repair", return_value=True) as mock_repair:
            fixed = run_repairs([_fail("bm25", repairable=True)], echo_fn=lambda _m: None)
        assert fixed[0]["repaired"] is True
        mock_repair.assert_called_once()


class TestRunChecks:

    def test_run_checks_updates_registry(self):
        from src.status import snapshot_status
        with patch("src.vector_store.embedding.get_embedding_model", return_value=MagicMock()):
            from src.monitor import run_checks
            results = run_checks(("embedding",), echo_fn=lambda _m: None)
        assert results[0]["ok"] is True
        assert snapshot_status()["embedding"]["state"] == "ready"

    def test_run_checks_unknown_name(self):
        from src.monitor import run_checks
        results = run_checks(("no_such_component",), echo_fn=lambda _m: None)
        assert results[0]["ok"] is False
        assert "未知" in results[0]["error"]


class TestMain:

    def test_main_all_ok_exit_0(self):
        import src.monitor as monitor_mod
        results = [_ok("embedding"), _ok("bm25"), _ok("graph")]
        with patch.object(monitor_mod, "run_checks", return_value=results):
            assert monitor_mod.main(["--json"]) == 0

    def test_main_fail_exit_1(self):
        import src.monitor as monitor_mod
        results = [_ok("embedding"), _fail("bm25", repairable=False)]
        with patch.object(monitor_mod, "run_checks", return_value=results):
            assert monitor_mod.main(["--json"]) == 1

    def test_main_repair_then_ok_exit_0(self):
        import src.monitor as monitor_mod
        fail = _fail("bm25", repairable=True)
        ok_ = _ok("bm25")
        checks = [fail, ok_]  # first pass fails, re-check passes
        with (
            patch.object(monitor_mod, "run_checks", side_effect=[checks[:1], checks[1:]]),
            patch.object(monitor_mod, "run_repairs", return_value=[{"name": "bm25", "repaired": True}]),
        ):
            assert monitor_mod.main(["--repair", "--json"]) == 0


class TestSelfCheckEntry:

    def test_selfcheck_json_ok(self):
        import selfcheck
        results = [_ok("embedding"), _ok("bm25"), _ok("graph")]
        with patch.object(selfcheck, "run_checks", return_value=results):
            assert selfcheck.main(["--json"]) == 0

    def test_selfcheck_json_fail(self):
        import selfcheck
        results = [_ok("embedding"), _fail("bm25", repairable=False)]
        with patch.object(selfcheck, "run_checks", return_value=results):
            assert selfcheck.main(["--json"]) == 1

    def test_selfcheck_repair_flag(self):
        import selfcheck
        results = [_ok("embedding"), _ok("bm25")]
        with (
            patch.object(selfcheck, "run_checks", return_value=results),
            patch.object(selfcheck, "run_repairs") as mock_repairs,
        ):
            assert selfcheck.main(["--repair", "--json"]) == 0
        mock_repairs.assert_called_once()

    def test_selfcheck_uses_project_root_syspath(self):
        import sys
        import selfcheck
        assert str(selfcheck.Path(__file__).resolve().parent.parent) in sys.path
