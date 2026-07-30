import json
import re

from config import GRAPH_LLM_BATCH_SIZE

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
    total_batches = (len(texts) + GRAPH_LLM_BATCH_SIZE - 1) // GRAPH_LLM_BATCH_SIZE

    for batch_idx in range(0, len(texts), GRAPH_LLM_BATCH_SIZE):
        batch = texts[batch_idx : batch_idx + GRAPH_LLM_BATCH_SIZE]
        combined = "\n---\n".join(batch)
        prompt = f"{SYSTEM_PROMPT}\n\n文档：\n{combined[:6000]}"
        current_batch_num = batch_idx // GRAPH_LLM_BATCH_SIZE + 1
        print(f"  [LLM抽取] 第 {current_batch_num}/{total_batches} 批 ({len(batch)} chunks) ...", end="")

        try:
            response = llm.invoke(prompt)
            data = _validate_entities(_parse_llm_response(response.content))
            print(" OK")
        except Exception as e:
            print(f" 降级到 jieba (原因: {e})")
            fallback_entities, fallback_relations = _fallback_batch(batch)
            for e in fallback_entities:
                key = (e["name"], e["type"])
                if key not in all_entities:
                    all_entities[key] = e
            for r in fallback_relations:
                rkey = (r["source"], r["target"], r["relation"])
                if rkey not in seen_relations:
                    seen_relations.add(rkey)
                    all_relations.append(r)
            continue

        for e in data["entities"]:
            key = (e["name"], e["type"])
            if key not in all_entities:
                all_entities[key] = {"name": e["name"], "type": e["type"], "count": 1}

        for r in data["relations"]:
            rkey = (r["source"], r["target"], r["relation"])
            if rkey not in seen_relations:
                seen_relations.add(rkey)
                all_relations.append(r)

    entities_list = [
        {"name": name, "type": etype, "count": info["count"]}
        for (name, etype), info in all_entities.items()
    ]
    return entities_list, all_relations
