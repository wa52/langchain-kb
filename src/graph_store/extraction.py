import jieba.posseg as pseg

TYPE_MAP = {
    "nr": "Person",
    "ns": "Location",
    "nz": "Technology",
    "eng": "Tool",
    "n": "Concept",
}
MAX_ENTITIES_PER_CHUNK = 15
EN_STOP_WORDS = {
    "the", "a", "an", "is", "are", "was", "were", "be", "been",
    "it", "its", "this", "that", "these", "those",
    "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "and", "or", "not", "no", "if", "but",
    "will", "can", "may", "would", "could", "should",
    "has", "have", "had", "do", "does", "did",
    "also", "very", "each", "all", "any", "both", "each",
    "use", "used", "using", "set", "get", "way",
    # URL / document structure noise
    "com", "www", "html", "https", "http", "org", "net",
    "source", "src", "ref", "md", "txt", "pdf",
    "overview", "summary", "description", "introduction",
}


def extract_entities(text: str) -> list[dict]:
    words = pseg.lcut(text)
    counter: dict[str, dict] = {}
    for w, flag in words:
        w = w.strip()
        if len(w) < 2:
            continue
        if flag == "eng" and w.lower() in EN_STOP_WORDS:
            continue
        etype = TYPE_MAP.get(flag)
        if etype is None:
            continue
        if w not in counter:
            counter[w] = {"name": w, "type": etype, "count": 0}
        counter[w]["count"] += 1
    entities = sorted(counter.values(), key=lambda x: x["count"], reverse=True)
    return [e for e in entities if e["count"] >= 3 and len(e["name"]) >= 2]


def extract_relations(texts: list[str]) -> list[dict]:
    seen: set[tuple[str, str]] = set()
    relations = []
    for text in texts:
        words = pseg.lcut(text)
        entity_positions: list[tuple[str, int]] = []
        for w, flag in words:
            w = w.strip()
            if len(w) < 2:
                continue
            if flag == "eng" and w.lower() in EN_STOP_WORDS:
                continue
            etype = TYPE_MAP.get(flag)
            if etype is None:
                continue
            pos = text.find(w)
            if pos != -1:
                entity_positions.append((w, pos))
        entity_positions.sort(key=lambda x: x[1])
        unique_entities = list(dict.fromkeys(e[0] for e in entity_positions))[:MAX_ENTITIES_PER_CHUNK]
        entities_set = set(unique_entities)
        # sentence-level: entities within same sentence
        sentences = text.replace("\n", " ").split("。")
        for sent in sentences:
            sent_ents = [e for e in unique_entities if e in sent]
            for i in range(len(sent_ents)):
                for j in range(i + 1, len(sent_ents)):
                    a, b = sent_ents[i], sent_ents[j]
                    key = (a, b) if a < b else (b, a)
                    if key not in seen:
                        seen.add(key)
                        relations.append({"source": key[0], "target": key[1], "relation": "co_occur", "strength": "strong"})
    return relations
