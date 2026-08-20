import json

import config


class TestGraphSnapshot:
    def _point_at(self, tmp_path):
        self._old_dir = config.GRAPH_PERSIST_DIR
        config.GRAPH_PERSIST_DIR = str(tmp_path)

    def _restore(self):
        config.GRAPH_PERSIST_DIR = self._old_dir

    def test_save_writes_snapshot_and_reloads_from_it(self, tmp_path):
        self._point_at(tmp_path)
        try:
            from src.graph_store.graph import KnowledgeGraph
            kg = KnowledgeGraph()
            kg.add_entity("VisionMaster", "软件", source="a.md")
            kg.add_relation("VisionMaster", "HALCON", "包含")
            kg.save()
            assert (tmp_path / "knowledge_graph.gpickle").exists()
            # Remove the JSON so a successful reload must come from the snapshot.
            (tmp_path / "knowledge_graph.json").unlink()
            kg2 = KnowledgeGraph()
            assert kg2.graph.number_of_nodes() == 2
            assert kg2.graph.number_of_edges() == 1
            assert kg2._entity_sources["VisionMaster"] == {"a.md"}
        finally:
            self._restore()

    def test_stale_snapshot_falls_back_to_json(self, tmp_path):
        self._point_at(tmp_path)
        try:
            from src.graph_store.graph import KnowledgeGraph
            (tmp_path / "knowledge_graph.json").write_text(
                json.dumps({"nodes": [{"id": "X", "type": "t", "count": 1, "sources": []}], "edges": []}),
                encoding="utf-8",
            )
            snap = tmp_path / "knowledge_graph.gpickle"
            snap.write_bytes(b"corrupt")
            import os
            os.utime(snap, (1, 1))  # older than the json -> ignored
            kg = KnowledgeGraph()
            assert kg.graph.number_of_nodes() == 1
            assert kg.graph.nodes["X"]["type"] == "t"
        finally:
            self._restore()
