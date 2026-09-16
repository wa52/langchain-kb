#!/usr/bin/env python
"""项目自检：一键诊断知识库各关键组件状态，可自动修复。

独立运行（无 CLI / API 依赖）：

  python selfcheck.py                  # 只读自检
  python selfcheck.py --repair          # 自检 + 自动修复失败且可修复的组件
  python selfcheck.py --check bm25,graph   # 只自检指定组件
  python selfcheck.py --json            # JSON 输出

自检范围：状态注册表 / 数据目录 / Embedding / LLM / 向量库 / BM25 索引 /
知识图谱 / RAG Agent / 索引任务 / 临时文件（共 10 项）。

退出码：0 全部通过；1 存在失败；2 自动修复后仍失败。
"""

import argparse
import io
import json
import sys
from pathlib import Path

# 保证从任意工作目录运行都能导入 src（项目自检按项目根解析）
sys.path.insert(0, str(Path(__file__).resolve().parent))

from src.monitor import COMPONENT_NAMES, run_checks, run_repairs  # noqa: E402

_TITLES = {
    "registry": "状态注册表",
    "data_dirs": "数据目录",
    "embedding": "Embedding 模型",
    "llm": "LLM 客户端",
    "vector_store": "向量库",
    "bm25": "BM25 索引",
    "graph": "知识图谱",
    "agent": "RAG Agent",
    "index": "索引任务",
    "tmp_files": "临时文件",
}

_MARKS = {"ready": "[OK]", "error": "[ER]", "pending": "[--]", "loading": "[..]"}


def _banner():
    from config import PRODUCT_NAME, KNOWLEDGE_HOME
    width = 58
    print("=" * width)
    print(f"  {PRODUCT_NAME} · 项目自检")
    print(f"  数据根目录: {KNOWLEDGE_HOME}")
    print("=" * width)


def _render_row(result: dict) -> str:
    mark = _MARKS.get(result.get("status", "pending"), "[--]")
    title = _TITLES.get(result["name"], result["name"])
    dur = f"  ({result.get('duration_ms', 0) / 1000:.1f}s)" if result.get("duration_ms") else ""
    return f"  {mark}  {title:<14}{result.get('detail', '')}{dur}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="selfcheck", description="项目自检：诊断关键组件并可选自动修复"
    )
    parser.add_argument("--repair", action="store_true", help="自动修复失败且可修复的组件")
    parser.add_argument("--check", default="", help="只自检指定组件（逗号分隔），默认全部")
    parser.add_argument("--json", action="store_true", help="JSON 输出")
    args = parser.parse_args(argv)

    names = tuple(n.strip() for n in args.check.split(",") if n.strip()) or COMPONENT_NAMES
    quiet = lambda _m: None  # noqa: E731 - 自检程序自行渲染报告

    _banner()
    results = run_checks(names, echo_fn=quiet)
    failed = [c for c in results if not c["ok"]]

    if args.repair:
        print("\n-- 自动修复 --")
        for r in run_repairs(failed, echo_fn=print):
            if r.get("repaired"):
                print(f"  {r['name']:<14} 修复成功")
            elif not r.get("skipped"):
                print(f"  {r['name']:<14} 修复失败")
        print("\n-- 修复后复查 --")
        results = run_checks(names, echo_fn=quiet)
        failed = [c for c in results if not c["ok"]]

    if args.json:
        print(json.dumps({
            "status": "ok" if not failed else "error",
            "data": {
                "checks": results,
                "passed": len(results) - len(failed),
                "total": len(results),
                "failed": [c["name"] for c in failed],
            },
        }, ensure_ascii=False))
        return 0 if not failed else (2 if args.repair else 1)

    print("\n-- 自检结果 --")
    for c in results:
        print(_render_row(c))
        if not c["ok"]:
            print(f"            修复建议: {c.get('fix') or '（不可自动修复，请按提示处理）'}")
    passed = len(results) - len(failed)
    verdict = "全部通过" if not failed else f"{len(failed)} 项异常"
    print("-" * 58)
    print(f"  通过 {passed}/{len(results)} · {verdict}")
    print("=" * 58)
    if failed and not args.repair:
        print("  提示: 运行  python selfcheck.py --repair  自动修复可修复项")
    return 0 if not failed else (2 if args.repair else 1)


if __name__ == "__main__":
    # Windows 终端可能是 GBK：强制 UTF-8/replace，避免中文打印崩溃
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")
    sys.exit(main())
