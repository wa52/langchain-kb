"""监控测试修复程序：探测各关键组件状态并尝试修复。

独立于 API/控制台运行，作为监控层（src/status.py）的主动测试工具：

  python -m src.monitor              # 只读：探测全部组件并汇报
  python -m src.monitor --repair      # 探测 + 自动修复失败且可修复的组件
  python -m src.monitor --check bm25,graph   # 只检查指定组件
  python -m src.monitor --json        # JSON 输出

也可经 CLI 调用：`knowledge monitor [--repair]`。

流程：
  1. run_checks()：逐组件探测（只读，可安全重复执行），并把结果回写监控层注册表，
     使 `/api/v1/status` 与控制台 `/status` 能反映实际探测状态；
  2. 失败且可自动修复的组件，用 repair(name) / run_repairs() 尝试修复；
  3. 修复后复查，输出修复前后状态对比。

退出码：0 全部通过；1 存在未修复的失败；2 自动修复失败。
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path
from typing import Any, Callable

from config import (
    CHROMA_PERSIST_DIR,
    DATA_DIR,
    DEEPSEEK_API_KEY,
    EXTERNAL_DIR,
    GRAPH_PERSIST_DIR,
    KNOWLEDGE_HOME,
)
from src.status import get_registry

# 判定注册表“卡在 loading”的阈值（秒）
STUCK_LOADING_SECONDS = 300.0
# 判定索引任务“卡在 running”的阈值（秒）
STUCK_TASK_SECONDS = 600.0

COMPONENT_NAMES = (
    "registry", "data_dirs", "embedding", "llm", "vector_store",
    "bm25", "graph", "agent", "index", "tmp_files",
)
# 与监控层注册表同名的检查项（探测结果会回写注册表）
_REGISTRY_MAPPED = ("embedding", "llm", "vector_store", "bm25", "graph", "agent", "index")


def _blank_result(name: str) -> dict[str, Any]:
    return {
        "name": name,
        "ok": True,
        "status": "pending",
        "detail": "",
        "error": None,
        "duration_ms": None,
        "fix": "",
        "repairable": False,
    }


def _check(name: str, fn: Callable[[], dict], echo_fn: Callable = print) -> dict:
    """执行一次探测：回写注册表（若该组件在监控范围内）并计时。"""
    reg = get_registry()
    if name in _REGISTRY_MAPPED:
        reg.set_loading(name, f"monitor 探测 {name}")
    t0 = time.time()
    try:
        result = fn()
    except Exception as e:  # noqa: BLE001 - 探测程序应捕获一切异常并汇报
        result = _blank_result(name)
        result.update(ok=False, status="error", error=str(e)[:500])
    # 统一状态字段：ok 即 ready，失败即 error（各检查项可能未显式设置）
    if result.get("ok") and result.get("status") != "ready":
        result["status"] = "ready"
    elif not result.get("ok") and result.get("status") not in ("error",):
        result["status"] = "error"
    result["duration_ms"] = round((time.time() - t0) * 1000.0, 1)
    if name in _REGISTRY_MAPPED:
        if result["ok"]:
            reg.set_ready(name, f"{result['detail']} · monitor")
        else:
            reg.set_error(name, result.get("error") or "monitor 探测失败", result["detail"])
    if echo_fn:
        echo_fn(f"[monitor] {name}: {'OK' if result['ok'] else 'FAIL'} - {result['detail'] or result.get('error') or ''}")
    return result


# ---------------------------------------------------------------------------
# 检查项
# ---------------------------------------------------------------------------

def _check_registry() -> dict:
    from src.status import DEFAULT_COMPONENTS, snapshot_status
    snap = snapshot_status()
    missing = [n for n in DEFAULT_COMPONENTS if n not in snap]
    stuck = []
    for name, c in snap.items():
        if c.get("state") == "loading" and c.get("started_at"):
            if (time.time() - c["started_at"]) > STUCK_LOADING_SECONDS:
                stuck.append(name)
    r = _blank_result("registry")
    if missing or stuck:
        r.update(
            ok=False,
            status="error",
            detail=f"缺组件 {missing} · 卡死 {stuck}",
            error="注册表状态异常",
            fix="运行: python -m src.monitor --repair",
            repairable=True,
        )
    else:
        r.update(detail=f"{len(snap)} 组件 · 无卡死")
    return r


def _check_data_dirs() -> dict:
    r = _blank_result("data_dirs")
    missing = [str(p) for p in (DATA_DIR, Path(EXTERNAL_DIR), Path(CHROMA_PERSIST_DIR)) if not p.exists()]
    if missing:
        r.update(
            ok=False, status="error", detail=f"缺少目录: {missing}",
            error="数据目录不存在", fix="运行: python -m src.monitor --repair",
            repairable=True,
        )
    else:
        r.update(detail=f"数据目录完整 ({KNOWLEDGE_HOME})")
    return r


def _check_embedding() -> dict:
    from src.vector_store.embedding import get_embedding_model
    model = get_embedding_model()
    r = _blank_result("embedding")
    r.update(detail=type(model).__name__, fix="检查 HF_ENDPOINT / 网络 / 模型缓存", repairable=False)
    return r


def _check_llm() -> dict:
    from src.llm import get_llm
    r = _blank_result("llm")
    if not DEEPSEEK_API_KEY:
        r.update(
            ok=False, status="error", detail="DEEPSEEK_API_KEY 未设置",
            error="缺少 API Key", fix="在 .env 中设置 DEEPSEEK_API_KEY", repairable=False,
        )
        return r
    llm = get_llm(temperature=0)
    r.update(detail=llm.model_name, fix="", repairable=False)
    return r


def _check_vector_store() -> dict:
    from src.vector_store.chroma_client import get_vector_store
    vs = get_vector_store()
    count = vs._collection.count()
    r = _blank_result("vector_store")
    r.update(detail=f"{count} chunks · {CHROMA_PERSIST_DIR}", repairable=False)
    if os.name == "nt" and not CHROMA_PERSIST_DIR.isascii():
        r.update(
            ok=False, status="error", detail=f"路径含非 ASCII 字符: {CHROMA_PERSIST_DIR}",
            error="ChromaDB 无法打开非 ASCII 路径", fix="设置 ASCII 的 CHROMA_PERSIST_DIR",
            repairable=False,
        )
    return r


def _check_bm25() -> dict:
    from src.retrieval import retriever as _ret
    r = _blank_result("bm25")
    bm25 = _ret._bm25_retriever
    if bm25 is not None:
        try:
            n = len(bm25.docs)
        except Exception:
            n = "?"
        r.update(detail=f"{n} chunks · 已在内存", repairable=False)
        return r
    if not _ret._BM25_PERSIST_PATH.exists():
        r.update(
            ok=False, status="error", detail="BM25 缓存不存在",
            error="未构建 BM25 索引", fix="运行: python -m src.monitor --repair",
            repairable=True,
        )
        return r
    # 缓存存在：若向量库可用则校验计数，否则按存在即通过
    try:
        from src.vector_store.chroma_client import get_vector_store
        expected = get_vector_store()._collection.count()
    except Exception:
        expected = None
    try:
        with open(_ret._BM25_PERSIST_PATH, "rb") as f:
            import pickle
            texts = pickle.load(f)["texts"]
    except Exception as e:
        r.update(
            ok=False, status="error", detail="BM25 缓存损坏",
            error=str(e)[:200], fix="运行: python -m src.monitor --repair", repairable=True,
        )
        return r
    if expected is not None and len(texts) != expected:
        r.update(
            ok=False, status="error", detail=f"缓存 {len(texts)} / 当前 {expected} 失效",
            error="BM25 缓存过期", fix="运行: python -m src.monitor --repair", repairable=True,
        )
    else:
        r.update(detail=f"{len(texts)} chunks · 磁盘缓存")
    return r


def _check_graph() -> dict:
    from src.graph_store.retriever import get_graph
    graph_path = Path(GRAPH_PERSIST_DIR) / "knowledge_graph.json"
    r = _blank_result("graph")
    if not graph_path.exists() or graph_path.stat().st_size == 0:
        r.update(
            ok=False, status="error", detail="知识图谱文件缺失或为空",
            error="图谱未构建", fix="运行: python -m src.monitor --repair",
            repairable=True,
        )
        return r
    kg = get_graph()
    nc = kg.graph.number_of_nodes()
    r.update(detail=f"{nc} 实体")
    if nc == 0:
        r.update(
            ok=False, status="error", detail="图谱文件存在但为空（可能损坏）",
            error="图谱损坏", fix="运行: python -m src.monitor --repair", repairable=True,
        )
    return r


def _check_agent() -> dict:
    from src.resources import ResourceManager
    from src.status import snapshot_status
    r = _blank_result("agent")
    rm = ResourceManager.get_instance()
    if rm.agent is not None:
        r.update(detail="已构建（缓存）", repairable=False)
        return r
    state = snapshot_status().get("agent", {}).get("state")
    if state == "error":
        r.update(
            ok=False, status="error", detail="上次构建失败",
            error=snapshot_status()["agent"].get("error") or "Agent 构建失败",
            fix="运行: python -m src.monitor --repair", repairable=True,
        )
        return r
    # Agent 惰性构建：未构建是正常状态
    r.update(detail="惰性构建（未构建，正常）", repairable=False)
    return r


def _check_index() -> dict:
    from src.api.services.indexing import get_task_manager
    r = _blank_result("index")
    mgr = get_task_manager()
    stuck = []
    for tid, t in mgr._tasks.items():
        if t.get("status") == "running" and t.get("created_at"):
            from datetime import datetime, timezone
            try:
                created = datetime.fromisoformat(t["created_at"])
                age = (datetime.now(timezone.utc) - created).total_seconds()
            except Exception:
                age = 0.0
            if age > STUCK_TASK_SECONDS:
                stuck.append(tid)
    if stuck:
        r.update(
            ok=False, status="error", detail=f"卡死任务 {stuck}",
            error="索引任务卡死", fix="运行: python -m src.monitor --repair", repairable=True,
        )
    else:
        r.update(detail="无卡死任务")
    return r


def _check_tmp_files() -> dict:
    leftovers = []
    for pattern in ("*.pkl.tmp", "*.tmp"):
        leftovers.extend(str(p) for p in Path(CHROMA_PERSIST_DIR).glob(pattern) if p.is_file())
        leftovers.extend(str(p) for p in Path(GRAPH_PERSIST_DIR).glob(pattern) if p.is_file())
    r = _blank_result("tmp_files")
    if leftovers:
        r.update(
            ok=False, status="error", detail=f"遗留临时文件 {len(leftovers)}",
            error="临时文件未清理", fix="运行: python -m src.monitor --repair", repairable=True,
        )
    else:
        r.update(detail="无遗留临时文件")
    return r


_CHECKERS = {
    "registry": _check_registry,
    "data_dirs": _check_data_dirs,
    "embedding": _check_embedding,
    "llm": _check_llm,
    "vector_store": _check_vector_store,
    "bm25": _check_bm25,
    "graph": _check_graph,
    "agent": _check_agent,
    "index": _check_index,
    "tmp_files": _check_tmp_files,
}


# ---------------------------------------------------------------------------
# 修复项
# ---------------------------------------------------------------------------

def _repair_registry(echo_fn: Callable = print) -> bool:
    from src.status import snapshot_status, get_registry
    fixed = False
    for name, c in snapshot_status().items():
        if c.get("state") == "loading" and c.get("started_at"):
            if (time.time() - c["started_at"]) > STUCK_LOADING_SECONDS:
                get_registry().set_ready(name, "monitor 修复：解除卡死")
                echo_fn(f"  [修复] {name}: 解除卡死 loading → ready")
                fixed = True
    return fixed


def _repair_data_dirs(echo_fn: Callable = print) -> bool:
    from config import ensure_data_dirs
    ensure_data_dirs()
    ok = all(p.exists() for p in (DATA_DIR, Path(EXTERNAL_DIR), Path(CHROMA_PERSIST_DIR)))
    if ok:
        echo_fn("  [修复] 数据目录已创建")
    return ok


def _repair_embedding(echo_fn: Callable = print) -> bool:
    from src.vector_store.embedding import get_embedding_model
    try:
        model = get_embedding_model()
        echo_fn(f"  [修复] embedding 重新加载成功: {type(model).__name__}")
        return True
    except Exception as e:
        echo_fn(f"  [修复] embedding 加载失败: {e}")
        return False


def _repair_llm(echo_fn: Callable = print) -> bool:
    echo_fn("  [修复] LLM 无法自动修复：请在 .env 中设置 DEEPSEEK_API_KEY")
    return False


def _repair_vector_store(echo_fn: Callable = print) -> bool:
    echo_fn("  [修复] 向量库无法自动修复：请检查 CHROMA_PERSIST_DIR 路径")
    return False


def _repair_bm25(echo_fn: Callable = print) -> bool:
    try:
        from src.vector_store.chroma_client import get_vector_store
        from src.retrieval.retriever import rebuild_bm25
        rebuild_bm25(get_vector_store(), echo_fn=echo_fn)
        return True
    except Exception as e:
        echo_fn(f"  [修复] BM25 重建失败: {e}")
        return False


def _repair_graph(echo_fn: Callable = print) -> bool:
    try:
        from src.graph_store.graph import build_graph_store
        from src.graph_store.retriever import set_graph
        kg = build_graph_store()
        set_graph(kg)
        echo_fn(f"  [修复] 知识图谱重建完成 ({kg.graph.number_of_nodes()} 实体)")
        return True
    except Exception as e:
        echo_fn(f"  [修复] 知识图谱重建失败: {e}")
        return False


def _repair_agent(echo_fn: Callable = print) -> bool:
    try:
        from src.agent.rag_agent import create_rag_agent
        agent = create_rag_agent()
        rm = ResourceManager_get()
        if rm is not None and rm.is_ready():
            rm.agent = agent
        echo_fn("  [修复] RAG Agent 构建成功")
        return True
    except Exception as e:
        echo_fn(f"  [修复] RAG Agent 构建失败: {e}")
        return False


def ResourceManager_get():
    try:
        from src.resources import ResourceManager
        return ResourceManager.get_instance()
    except Exception:
        return None


def _repair_index(echo_fn: Callable = print) -> bool:
    from datetime import datetime, timezone
    from src.api.services.indexing import get_task_manager
    mgr = get_task_manager()
    fixed = False
    for tid, t in list(mgr._tasks.items()):
        if t.get("status") == "running":
            try:
                created = datetime.fromisoformat(t["created_at"])
                age = (datetime.now(timezone.utc) - created).total_seconds()
            except Exception:
                age = STUCK_TASK_SECONDS + 1
            if age > STUCK_TASK_SECONDS:
                mgr.update_task(tid, status="failed", error="monitor 修复：任务卡死已终止")
                echo_fn(f"  [修复] 索引任务 {tid} 已标记失败（卡死）")
                fixed = True
    return fixed


def _repair_tmp_files(echo_fn: Callable = print) -> bool:
    removed = 0
    for pattern in ("*.pkl.tmp", "*.tmp"):
        for p in list(Path(CHROMA_PERSIST_DIR).glob(pattern)):
            try:
                p.unlink()
                removed += 1
                echo_fn(f"  [修复] 删除临时文件: {p}")
            except OSError:
                pass
        for p in list(Path(GRAPH_PERSIST_DIR).glob(pattern)):
            try:
                p.unlink()
                removed += 1
                echo_fn(f"  [修复] 删除临时文件: {p}")
            except OSError:
                pass
    return removed > 0


_REPAIRERS = {
    "registry": _repair_registry,
    "data_dirs": _repair_data_dirs,
    "embedding": _repair_embedding,
    "llm": _repair_llm,
    "vector_store": _repair_vector_store,
    "bm25": _repair_bm25,
    "graph": _repair_graph,
    "agent": _repair_agent,
    "index": _repair_index,
    "tmp_files": _repair_tmp_files,
}


# ---------------------------------------------------------------------------
# 对外 API
# ---------------------------------------------------------------------------

def run_checks(names: tuple[str, ...] = COMPONENT_NAMES, echo_fn: Callable = print) -> list[dict]:
    """探测指定组件，返回逐项结果。只读，可安全重复执行。"""
    results = []
    for name in names:
        fn = _CHECKERS.get(name)
        if fn is None:
            r = _blank_result(name)
            r.update(ok=False, status="error", error=f"未知检查项: {name}")
            results.append(r)
            continue
        results.append(_check(name, fn, echo_fn=echo_fn))
    return results


def repair(name: str, echo_fn: Callable = print) -> bool:
    """尝试修复单个组件，返回是否修复成功（或已无可修复项）。"""
    fn = _REPAIRERS.get(name)
    if fn is None:
        return False
    return fn(echo_fn=echo_fn)


def run_repairs(failures: list[dict], echo_fn: Callable = print) -> list[dict]:
    """修复所有失败且可自动修复的检查项，返回修复结果列表。"""
    fixed = []
    for c in failures:
        if not c.get("ok") and c.get("repairable"):
            try:
                ok = repair(c["name"], echo_fn=echo_fn)
            except Exception as e:  # noqa: BLE001
                ok = False
                echo_fn(f"  [修复] {c['name']} 异常: {e}")
            fixed.append({"name": c["name"], "repaired": ok})
        else:
            fixed.append({"name": c["name"], "repaired": False, "skipped": True})
    return fixed


# ---------------------------------------------------------------------------
# 独立运行入口
# ---------------------------------------------------------------------------

def _ascii_row(result: dict) -> str:
    mark = {"ok": "[OK]", "error": "[ER]", "pending": "[--]", "loading": "[..]"}.get(
        result.get("status", "pending"), "[--]"
    )
    dur = f" {result.get('duration_ms', 0) / 1000:.1f}s" if result.get("duration_ms") else ""
    return f"  {mark:<5} {result['name']:<14} {result.get('detail', '')}{dur}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="monitor", description="监控测试修复程序")
    parser.add_argument("--repair", action="store_true", help="自动修复失败且可修复的组件")
    parser.add_argument("--check", default="", help="只检查指定组件（逗号分隔），默认全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    names = tuple(n.strip() for n in args.check.split(",") if n.strip()) or COMPONENT_NAMES
    echo_fn = (lambda _m: None) if args.json else print

    print("==== 监控测试修复程序 ====")
    results = run_checks(names, echo_fn=echo_fn)
    failed = [c for c in results if not c["ok"]]

    if args.repair:
        print("\n-- 自动修复 --")
        repairs = run_repairs(failed, echo_fn=print)
        for r in repairs:
            print(f"  {r['name']:<14} {'修复成功' if r.get('repaired') else ('跳过' if r.get('skipped') else '修复失败')}")
        print("\n-- 修复后复查 --")
        results = run_checks(names, echo_fn=echo_fn)
        failed = [c for c in results if not c["ok"]]

    if args.json:
        import json
        print(json.dumps({
            "status": "ok" if not failed else "error",
            "data": {
                "checks": results,
                "passed": len(results) - len(failed),
                "total": len(results),
                "failed": [c["name"] for c in failed],
            },
        }, ensure_ascii=False))
    else:
        print("\n-- 检查结果 --")
        for c in results:
            print(_ascii_row(c))
            if not c["ok"]:
                print(f"         修复建议: {c.get('fix') or '（不可自动修复）'}")
        print(f"\n通过 {len(results) - len(failed)}/{len(results)}" + ("，存在失败项" if failed else "，全部通过"))

    if failed:
        if args.repair:
            return 2
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
