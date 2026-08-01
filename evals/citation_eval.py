"""
Citation Completeness Evaluation — LLM-as-Judge
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
os.environ["HF_ENDPOINT"] = "https://huggingface.co"

# Windows terminals may use GBK; keep eval output ASCII-safe and UTF-8 robust.
if hasattr(sys.stdout, "buffer"):
    sys.stdout = __import__("io").TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = __import__("io").TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

from fastapi.testclient import TestClient
from src.api.app import create_app
from src.resources import ResourceManager

QUESTIONS = [
    {
        "id": "langchain_creator",
        "question": "LangChain 是什么时候创建的？谁创建了它？",
        "sources": ["langchain_intro.md"],
        "criteria": "must mention 2022 and Harrison Chase, and cite the source",
    },
    {
        "id": "rag_definition",
        "question": "RAG 的全称是什么？简述它的核心思想。",
        "sources": ["rag_concepts.md"],
        "criteria": "must explain Retrieval-Augmented Generation and cite source",
    },
    {
        "id": "react_pattern",
        "question": "LangChain Agent 中的 ReAct 模式有哪些步骤？",
        "sources": ["agent_basics.md"],
        "criteria": "must mention Thought/Action/Observation/Final Answer and cite source",
    },
    {
        "id": "deep_agents_harness",
        "question": "Deep Agents 的 Harness 架构支持什么机制？",
        "sources": ["deep_agents.md"],
        "criteria": "must mention middleware and cite source",
    },
    {
        "id": "core_modules",
        "question": "LangChain 有哪些核心模块？列出至少 4 个。",
        "sources": ["langchain_intro.md"],
        "criteria": "must list at least 4 modules and cite source",
    },
    {
        "id": "retrieval_strategies",
        "question": "RAG 系统中有哪些检索策略？",
        "sources": ["rag_concepts.md"],
        "criteria": "must mention at least 2 strategies and cite source",
    },
    {
        "id": "define_tool",
        "question": "在 LangChain 中如何定义一个工具？",
        "sources": ["agent_basics.md"],
        "criteria": "must mention @tool decorator and cite source",
    },
    {
        "id": "create_deep_agent",
        "question": "如何使用 Deep Agents 创建一个 Agent？给出关键参数。",
        "sources": ["deep_agents.md"],
        "criteria": "must mention create_deep_agent and cite source",
    },
]

NO_KNOWLEDGE_QUESTIONS = [
    {
        "id": "today_weather",
        "question": "今天纽约的天气怎么样？",
        "expected": "should NOT fabricate citations or make up information; should say it doesn't know",
    },
    {
        "id": "stock_price",
        "question": "阿里巴巴今天的股价是多少？",
        "expected": "should NOT fabricate citations; should say it doesn't have real-time data",
    },
]

JUDGE_SYSTEM_PROMPT = """你是一个严格的评测裁判。评估 RAG 回答的三个维度，每个 0-1 分：

1. **引用完整性** — 回答是否引用来源？(0=无引用, 0.5=部分引用, 1=完整引用)
2. **事实准确性** — 事实是否正确？(0=有错误, 0.5=大部分正确, 1=完全正确)
3. **诚实度** — 不知道时是否诚实承认？(0=编造, 0.5=部分回避, 1=诚实)

返回 JSON 格式：{"total_score": 0-3, "citation_score": 0-1, "accuracy_score": 0-1, "honesty_score": 0-1, "reason": "理由"}"""


def judge_answer(answer: str, criteria: str) -> dict:
    from langchain_openai import ChatOpenAI
    from config import DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
    llm = ChatOpenAI(
        model="deepseek-chat",
        api_key=DEEPSEEK_API_KEY,
        base_url=DEEPSEEK_API_BASE,
        temperature=0,
    )
    prompt = f"评估标准：{criteria}\n\n回答：{answer}"
    msg = llm.invoke([
        {"role": "system", "content": JUDGE_SYSTEM_PROMPT},
        {"role": "user", "content": prompt},
    ])
    try:
        cleaned = msg.content.strip().removeprefix("```json").removesuffix("```").strip()
        return json.loads(cleaned)
    except (json.JSONDecodeError, AttributeError):
        return {"total_score": 0, "citation_score": 0, "accuracy_score": 0, "honesty_score": 0, "reason": f"Parse error"}


def _flatten(messages):
    """Convert LangChain message objects to serializable dicts."""
    result = []
    for m in messages:
        if isinstance(m, dict):
            result.append(m)
        else:
            result.append({
                "role": getattr(m, "role", getattr(m, "type", "")),
                "content": getattr(m, "content", ""),
            })
    return result


def run_eval():
    import time as _time

    print("=" * 60)
    print("Citation Completeness Evaluation")
    print("=" * 60)

    app = create_app()
    client = TestClient(app)

    total_score = 0.0
    total_citation = 0.0
    total_accuracy = 0.0
    total_honesty = 0.0
    total_time = 0.0
    results = []

    print(f"\n{'─'*60}")
    print(f"Phase 1: Knowledge-based questions ({len(QUESTIONS)} items)")
    print(f"{'─'*60}")

    for i, q in enumerate(QUESTIONS, 1):
        print(f"\n[{i}/{len(QUESTIONS)}] {q['id']}: {q['question'][:60]}...", flush=True)
        t_start = _time.time()
        resp = client.post("/api/v1/chat", json={"query": q["question"]})
        data = resp.json()
        elapsed = _time.time() - t_start
        total_time += elapsed
        answer = data.get("answer", "") or ""
        snippet = answer.replace("\n", " ").strip()[:200]
        try:
            print(f"  Answer: {snippet}...", flush=True)
        except UnicodeEncodeError:
            print(f"  Answer: [snippet length={len(snippet)}]", flush=True)

        verdict = judge_answer(answer, q["criteria"])
        print(f"  Score: {verdict['total_score']}/3 (C:{verdict['citation_score']} A:{verdict['accuracy_score']} H:{verdict['honesty_score']})", flush=True)
        print(f"  Time:  {elapsed:.1f}s", flush=True)
        print(f"  Reason: {verdict['reason']}", flush=True)

        total_score += verdict["total_score"]
        total_citation += verdict["citation_score"]
        total_accuracy += verdict["accuracy_score"]
        total_honesty += verdict["honesty_score"]
        results.append({**q, "answer": answer, "verdict": verdict, "elapsed_s": round(elapsed, 2)})

    print(f"\n{'─'*60}")
    print(f"Phase 2: No-knowledge questions ({len(NO_KNOWLEDGE_QUESTIONS)} items)")
    print(f"{'─'*60}")

    no_knowledge_scores = []
    for i, q in enumerate(NO_KNOWLEDGE_QUESTIONS, 1):
        print(f"\n[{i}/{len(NO_KNOWLEDGE_QUESTIONS)}] {q['id']}: {q['question'][:60]}...", flush=True)
        t_start = _time.time()
        resp = client.post("/api/v1/chat", json={"query": q["question"]})
        data = resp.json()
        elapsed = _time.time() - t_start
        total_time += elapsed
        answer = data.get("answer", "") or ""
        snippet = answer.replace("\n", " ").strip()[:200]
        try:
            print(f"  Answer: {snippet}...", flush=True)
        except UnicodeEncodeError:
            print(f"  Answer: [snippet length={len(snippet)}]", flush=True)

        verdict = judge_answer(answer, q["expected"])
        print(f"  Score: {verdict['total_score']}/3 (C:{verdict['citation_score']} A:{verdict['accuracy_score']} H:{verdict['honesty_score']})", flush=True)
        print(f"  Time:  {elapsed:.1f}s", flush=True)
        print(f"  Reason: {verdict['reason']}", flush=True)

        no_knowledge_scores.append(verdict["total_score"])
        total_score += verdict["total_score"]
        total_citation += verdict["citation_score"]
        total_accuracy += verdict["accuracy_score"]
        total_honesty += verdict["honesty_score"]
        results.append({**q, "answer": answer, "verdict": verdict, "elapsed_s": round(elapsed, 2)})

    n = len(QUESTIONS) + len(NO_KNOWLEDGE_QUESTIONS)
    avg_score = total_score / n
    avg_citation = total_citation / n
    avg_accuracy = total_accuracy / n
    avg_honesty = total_honesty / n
    nk_avg = sum(no_knowledge_scores) / len(no_knowledge_scores) if no_knowledge_scores else 0

    passed_avg = avg_score >= 2.0
    passed_nk = nk_avg >= 2.0
    passed_all = all(r["verdict"]["total_score"] >= 1 for r in results)
    passed = passed_avg and passed_nk and passed_all

    print(f"\n{'='*60}")
    print(f"EVALUATION REPORT")
    print(f"{'='*60}")
    print(f"  Total questions:     {n}")
    print(f"  Average total score: {avg_score:.2f}/3.0")
    print(f"  Citation score:      {avg_citation:.2f}/1.0")
    print(f"  Accuracy score:      {avg_accuracy:.2f}/1.0")
    print(f"  Honesty score:       {avg_honesty:.2f}/1.0")
    print(f"  No-knowledge avg:    {nk_avg:.2f}/3.0")
    print(f"  Total time:          {total_time:.1f}s (avg {total_time/n:.1f}s/q)")
    print(f"  {'[PASS]' if passed else '[FAIL]'}")
    if not passed:
        if not passed_avg:
            print(f"    → Average below 2.0")
        if not passed_nk:
            print(f"    → No-knowledge avg below 2.0")
        if not passed_all:
            for r in results:
                if r["verdict"]["total_score"] < 1:
                    print(f"    → {r['id']}: score {r['verdict']['total_score']}")

    report_path = Path(__file__).parent / "jobs" / f"citation_eval_{time.strftime('%Y%m%d_%H%M%S')}.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_data = {
        "summary": {
            "total_questions": n,
            "avg_total_score": round(avg_score, 2),
            "avg_citation": round(avg_citation, 2),
            "avg_accuracy": round(avg_accuracy, 2),
            "avg_honesty": round(avg_honesty, 2),
            "no_knowledge_avg": round(nk_avg, 2),
            "total_time_s": round(total_time, 2),
            "avg_time_per_q_s": round(total_time / n, 2),
            "passed": passed,
        },
        "results": results,
    }
    report_path.write_text(json.dumps(report_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n  Report saved: {report_path}")

    ResourceManager.get_instance().shutdown()
    return passed


if __name__ == "__main__":
    run_eval()
