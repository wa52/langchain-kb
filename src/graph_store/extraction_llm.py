import json
import re

from config import GRAPH_LLM_BATCH_SIZE, GRAPH_LLM_CONCURRENCY

ENTITY_TYPE_WHITELIST = {
    "Framework", "Library", "Concept", "API", "Tool", "Language", "Person", "Technology"
}

SYSTEM_PROMPT = (
    "你是一个实体关系抽取助手。从以下文档中提取实体和关系。\n\n"
    "实体类型：Framework / Library / Concept / API / Tool / Language / Person / Technology\n"
    "关系类型：uses / depends_on / extends / implements / supports / belongs_to / related\n\n"
    "输出 JSON（只输出 JSON，不要其他文字）：\n"
    '{\n'
    '  "entities": [{"name": "...", "type": "..."}],\n'
    '  "relations": [{"source": "...", "target": "...", "relation": "..."}]\n'
    '}'
)


def _parse_llm_response(text: str) -> dict:
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        text = match.group(1).strip()
    return json.loads(text)


def _validate_entities(data: dict) -> dict:
    validated = {"entities": [], "relations": []}
    for e in data.get("entities", []):
        name = (e.get("name") or "").strip()
        etype = e.get("type", "Unknown")
        if not name:
            continue
        if etype not in ENTITY_TYPE_WHITELIST:
            etype = "Unknown"
        validated["entities"].append({"name": name, "type": etype})
    validated["relations"] = data.get("relations", [])
    return validated


def _fallback_batch(texts: list[str]):
    from src.graph_store.extraction import extract_entities, extract_relations
    entities: dict[tuple[str, str], dict] = {}
    for text in texts:
        for e in extract_entities(text):
            key = (e["name"], e["type"])
            if key not in entities:
                entities[key] = {"name": e["name"], "type": e["type"], "count": 0}
            entities[key]["count"] += 1
    rels = extract_relations(texts)
    return list(entities.values()), rels


def _extract_batch(batch: list[str], llm) -> tuple[list[dict], list[dict]]:
    """One batch of LLM extraction; falls back to jieba on any failure.

    Returns normalized ``[{name, type, count}]`` entities and relations, so the
    caller can merge results regardless of whether LLM or jieba produced them.
    """
    combined = "\n---\n".join(batch)
    prompt = f"{SYSTEM_PROMPT}\n\n文档：\n{combined[:6000]}"
    try:
        response = llm.invoke(prompt)
        data = _validate_entities(_parse_llm_response(response.content))
        entities = [
            {"name": e["name"], "type": e["type"], "count": 1} for e in data["entities"]
        ]
        return entities, data["relations"]
    except Exception:
        fallback_entities, fallback_relations = _fallback_batch(batch)
        entities = [
            {"name": e["name"], "type": e["type"], "count": e.get("count", 1)}
            for e in fallback_entities
        ]
        return entities, fallback_relations


def extract_entities_llm_batch(
    texts: list[str],
    llm=None,
) -> tuple[list[dict], list[dict]]:
    if llm is None:
        from src.llm import get_llm
        llm = get_llm(temperature=0)
    all_entities: dict[tuple[str, str], dict] = {}
    all_relations = []
    seen_relations: set[tuple[str, str, str]] = set()

    def merge(entities: list[dict], relations: list[dict]):
        for e in entities:
            key = (e["name"], e["type"])
            if key not in all_entities:
                all_entities[key] = e
        for r in relations:
            rkey = (r["source"], r["target"], r["relation"])
            if rkey not in seen_relations:
                seen_relations.add(rkey)
                all_relations.append(r)

    batches = [texts[i : i + GRAPH_LLM_BATCH_SIZE] for i in range(0, len(texts), GRAPH_LLM_BATCH_SIZE)]
    total_batches = len(batches)
    if total_batches == 0:
        return [], []

    if total_batches == 1:
        merge(*_extract_batch(batches[0], llm))
    else:
        # 每批独立调用 DeepSeek，并发跑；主线程归并，保持确定性去重。
        from concurrent.futures import ThreadPoolExecutor, as_completed

        done = 0
        with ThreadPoolExecutor(max_workers=max(1, GRAPH_LLM_CONCURRENCY)) as pool:
            futures = [pool.submit(_extract_batch, b, llm) for b in batches]
            for fut in as_completed(futures):
                done += 1
                print(
                    f"\r  [LLM抽取] 完成 {done}/{total_batches} 批 "
                    f"({GRAPH_LLM_CONCURRENCY} 并发) ...",
                    end="",
                )
                merge(*fut.result())
        print()

    entities_list = [
        {"name": name, "type": etype, "count": info["count"]}
        for (name, etype), info in all_entities.items()
    ]
    return entities_list, all_relations
