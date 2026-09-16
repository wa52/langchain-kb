from unittest.mock import patch


class TestSaveResearchMaterial:
    def test_rejects_short_material(self):
        from src.agent.tools import save_research_material

        result = save_research_material.invoke({"title": "x", "content": "short"})
        assert "至少" in result

    def test_saves_curated_material_and_uses_index_pipeline(self, tmp_path):
        from src.agent.tools import save_research_material

        captured = {}

        def fake_add(path, external_dir, echo_fn):
            captured["text"] = open(path, encoding="utf-8").read()
            return 3

        with (
            patch("config.EXTERNAL_DIR", str(tmp_path)),
            patch("src.ingestion.pipeline.run_add_path", side_effect=fake_add),
        ):
            result = save_research_material.invoke({
                "title": "Camera Guide",
                "content": "Reliable camera exposure and lighting setup. " * 8,
                "sources": "- https://example.com/camera",
            })

        assert "已将研究资料加入知识库" in result
        assert "Camera Guide" in captured["text"]
        assert "https://example.com/camera" in captured["text"]

    def test_rejects_oversized_material(self):
        from src.agent.tools import save_research_material

        result = save_research_material.invoke({
            "title": "large",
            "content": "x" * 200_001,
        })
        assert "超过 200 KB" in result
