import json
import time
from pathlib import Path
from collections import Counter
from typing import Callable, Optional

import networkx as nx

import config as cfg
from src.graph_store.extraction import extract_entities, extract_relations


class KnowledgeGraph:
    def __init__(self, echo_fn: Callable = print):
        self.echo_fn = echo_fn
        self.path = Path(cfg.GRAPH_PERSIST_DIR) / "knowledge_graph.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists():
            self._load()
        else:
            self.graph = nx.DiGraph()
            self._entity_count: Counter = Counter()
            self._entity_sources: dict[str, set] = {}

    def add_entity(self, name: str, etype: str, source: str | None = None):
        self.graph.add_node(name, type=etype)
        self._entity_count[name] += 1
        if source:
            self._entity_sources.setdefault(name, set()).add(source)

    def add_relation(self, source: str, target: str, relation: str, strength: str = "weak"):
        if self.graph.has_edge(source, target):
            edge = self.graph.edges[source, target]
            if isinstance(edge.get("relations"), list):
                if relation not in edge["relations"]:
                    edge["relations"].append(relation)
            else:
                self.graph.edges[source, target]["relations"] = [relation]
            self.graph.edges[source, target]["strength"] = strength
        else:
            self.graph.add_edge(source, target, relations=[relation], strength=strength)

    def build_from_chunks(self, chunks: list, llm=None, echo_fn: Optional[Callable] = None):
        echo_fn = echo_fn or self.echo_fn
        t0 = time.time()
        if self.graph.number_of_nodes() > 0:
            _saved = (self.graph.copy(), self._entity_count.copy(), {k: set(v) for k, v in self._entity_sources.items()})
        else:
            _saved = None
        self.clear()
        try:
            texts = [c.page_content for c in chunks]
            total = len(texts)

            if cfg.ENABLE_GRAPH_LLM_EXTRACTION:
                echo_fn(f"  [LLM模式] 共 {total} chunks, 批量{cfg.GRAPH_LLM_BATCH_SIZE}/批 ...")
                from src.graph_store.extraction_llm import extract_entities_llm_batch
                entities, rels = extract_entities_llm_batch(texts, llm=llm)
                all_entity_names: set[str] = set()
                for e in entities:
                    name = e["name"]
                    all_entity_names.add(name)
                    self.add_entity(name, e["type"])
                for r in rels:
                    if r["source"] in all_entity_names and r["target"] in all_entity_names:
                        self.add_relation(r["source"], r["target"], r["relation"], "strong")
            else:
                all_entities: dict[str, str] = {}
                for i, text in enumerate(texts):
                    source = chunks[i].metadata.get("source", "unknown") if hasattr(chunks[i], "metadata") else "unknown"
                    entities = extract_entities(text)
                    for e in entities:
                        name = e["name"]
                        if name not in all_entities:
                            all_entities[name] = e["type"]
                        self.add_entity(name, e["type"], source)
                    if (i + 1) % 50 == 0 or i == total - 1:
                        echo_fn(f"\r  [{i+1}/{total}] 实体抽取中...", end="")
                rels = extract_relations(texts)
                for r in rels:
                    if r["source"] in all_entities and r["target"] in all_entities:
                        self.add_relation(r["source"], r["target"], r["relation"], r["strength"])

            elapsed = time.time() - t0
            nc = self.graph.number_of_nodes()
            ec = self.graph.number_of_edges()
            echo_fn(f"  -> 知识图谱构建完成 ({nc} 实体, {ec} 关系, {elapsed:.1f}s)")
        except Exception:
            if _saved is not None:
                self.graph, self._entity_count, self._entity_sources = _saved
            raise

    def search(self, query: str, max_nodes: int = 30) -> str:
        query_lower = query.lower()
        matched = set()
        for node in self.graph.nodes():
            if query_lower in node.lower():
                matched.add(node)
        if not matched:
            return "未找到相关的图谱信息。"
        subgraph_nodes = set(matched)
        frontier = set(matched)
        depth = 2
        while depth > 0 and len(subgraph_nodes) < max_nodes:
            new_nodes = set()
            for node in frontier:
                for neighbor in self.graph.successors(node):
                    if neighbor not in subgraph_nodes:
                        new_nodes.add(neighbor)
                for neighbor in self.graph.predecessors(node):
                    if neighbor not in subgraph_nodes:
                        new_nodes.add(neighbor)
            if not new_nodes:
                break
            remaining = max_nodes - len(subgraph_nodes)
            new_nodes = set(list(new_nodes)[:remaining])
            subgraph_nodes.update(new_nodes)
            frontier = new_nodes
            depth -= 1
        subgraph = self.graph.subgraph(subgraph_nodes)
        lines = []
        for node in sorted(subgraph.nodes()):
            ndata = subgraph.nodes[node]
            etype = ndata.get("type", "Unknown")
            sources = self._entity_sources.get(node, set())
            source_str = ""
            if sources:
                srcs = list(sources)[:3]
                source_str = f" [{', '.join(srcs)}]"
            lines.append(f"  {node} ({etype}){source_str}")
            for _, target, edata in subgraph.out_edges(node, data=True):
                rels = ", ".join(edata.get("relations", ["related"]))
                lines.append(f"    └─ {rels} → {target}")
        if not lines:
            return "未找到相关的图谱信息。"
        return f"知识图谱查询结果:\n" + "\n".join(lines)

    def stats(self) -> dict:
        return {
            "entities": self.graph.number_of_nodes(),
            "relations": self.graph.number_of_edges(),
            "types": dict(Counter(
                ndata.get("type", "Unknown")
                for _, ndata in self.graph.nodes(data=True)
            )),
        }

    def save(self):
        data = {
            "nodes": [
                {"id": n, "type": ndata.get("type", "Unknown"),
                 "count": self._entity_count.get(n, 1),
                 "sources": list(self._entity_sources.get(n, set()))}
                for n, ndata in self.graph.nodes(data=True)
            ],
            "edges": [
                {"source": u, "target": v,
                 "relations": edata.get("relations", ["related"]),
                 "strength": edata.get("strength", "weak")}
                for u, v, edata in self.graph.edges(data=True)
            ],
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def _load(self):
        self.graph = nx.DiGraph()
        self._entity_count = Counter()
        self._entity_sources = {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            self.echo_fn("  [警告] 知识图谱文件损坏，使用空图谱")
            return
        for n in data.get("nodes", []):
            self.graph.add_node(n["id"], type=n.get("type", "Unknown"))
            self._entity_count[n["id"]] = n.get("count", 1)
            self._entity_sources[n["id"]] = set(n.get("sources", []))
        for e in data.get("edges", []):
            self.graph.add_edge(
                e["source"], e["target"],
                relations=e.get("relations", ["related"]),
                strength=e.get("strength", "weak"),
            )

    def add_chunks(self, chunks: list, llm=None, echo_fn: Optional[Callable] = None):
        echo_fn = echo_fn or self.echo_fn
        texts = [c.page_content for c in chunks]
        total = len(texts)
        if total == 0:
            return

        if cfg.ENABLE_GRAPH_LLM_EXTRACTION:
            from src.graph_store.extraction_llm import extract_entities_llm_batch
            echo_fn(f"  [LLM模式-增量] {total} chunks ...")
            entities, rels = extract_entities_llm_batch(texts, llm=llm)
            for e in entities:
                self.add_entity(e["name"], e["type"])
            for r in rels:
                if self.graph.has_node(r["source"]) and self.graph.has_node(r["target"]):
                    self.add_relation(r["source"], r["target"], r["relation"], "strong")
        else:
            for i, text in enumerate(texts):
                source = chunks[i].metadata.get("source", "unknown") if hasattr(chunks[i], "metadata") else "unknown"
                entities = extract_entities(text)
                for e in entities:
                    self.add_entity(e["name"], e["type"], source)
            rels = extract_relations(texts)
            for r in rels:
                if self.graph.has_node(r["source"]) and self.graph.has_node(r["target"]):
                    self.add_relation(r["source"], r["target"], r["relation"], r["strength"])
        echo_fn(f"  -> 增量合并完成 (当前共 {self.graph.number_of_nodes()} 实体, {self.graph.number_of_edges()} 关系)")

    def clear(self):
        self.graph.clear()
        self._entity_count.clear()
        self._entity_sources.clear()


def build_graph_store():
    from src.ingestion.loader import MarkdownLoader, load_path
    from config import DATA_DIR, EXTERNAL_DIR
    kg = KnowledgeGraph()
    texts_dir = Path(DATA_DIR)
    if texts_dir.exists():
        kg.echo_fn(f"  [1/2] Loading documents from {texts_dir} ...")
        loader = MarkdownLoader(texts_dir, echo_fn=kg.echo_fn)
        docs = loader.load_all()
    else:
        docs = []
    ext_dir = Path(EXTERNAL_DIR)
    if ext_dir.exists():
        ext_docs = load_path(ext_dir, echo_fn=kg.echo_fn)
        docs.extend(ext_docs)
    if not docs:
        kg.echo_fn("  未找到文档")
        return kg
    kg.echo_fn(f"  [2/2] Building knowledge graph from {len(docs)} documents ...")
    llm = None
    if cfg.ENABLE_GRAPH_LLM_EXTRACTION:
        from langchain_openai import ChatOpenAI
        from config import LLM_MODEL, DEEPSEEK_API_KEY, DEEPSEEK_API_BASE
        llm = ChatOpenAI(
            model=LLM_MODEL,
            api_key=DEEPSEEK_API_KEY,
            base_url=DEEPSEEK_API_BASE,
            temperature=0,
        )
    kg.build_from_chunks(docs, llm=llm)
    kg.save()
    return kg
