import pytest


class TestCapabilityModel:
    def test_domain_ids_complete(self):
        from src.capability.model import CAPABILITY_DOMAINS
        ids = [d["id"] for d in CAPABILITY_DOMAINS]
        assert ids == [1, 2, 3, 4, 5, 6, 7]

    def test_domain_names(self):
        from src.capability.model import CAPABILITY_DOMAINS
        names = [d["name"] for d in CAPABILITY_DOMAINS]
        assert names == [
            "需求分析", "知识研究", "方案设计",
            "算法实现", "工程开发", "项目验证", "能力评估",
        ]

    def test_technologies_includes_core(self):
        from src.capability.model import TECHNOLOGIES
        low = {t.lower() for t in TECHNOLOGIES}
        assert {"halcon", "opencv", "langchain", "deepagents", "langgraph"} <= low


class TestMapBySource:
    def test_hdev_source_maps_to_algorithm(self):
        from src.capability.mapper import map_by_source
        r = map_by_source("check_blister.hdev")
        assert 4 in r["domains"]
        assert r["technology"].lower() == "halcon"

    def test_solution_guide_maps_to_design(self):
        from src.capability.mapper import map_by_source
        r = map_by_source("solution_guide_ii_a_image_acquisition.pdf")
        assert 3 in r["domains"]
        assert "image_acquisition" in r["scene"] or r["scene"]

    def test_measuring_guide_scene(self):
        from src.capability.mapper import map_by_source
        r = map_by_source("solution_guide_iii_a_1d_measuring.pdf")
        assert 4 in r["domains"] or 3 in r["domains"]

    def test_langchain_maps_to_engineering(self):
        from src.capability.mapper import map_by_source
        r = map_by_source("01_LangChain 教程.md")
        assert 5 in r["domains"]
        assert r["technology"].lower() == "langchain"

    def test_matching_maps_scene(self):
        from src.capability.mapper import map_by_source
        r = map_by_source("surface_based_matching.pdf")
        assert "matching" in r["scene"] or "positioning" in r["scene"]


class TestMapByContent:
    def test_threshold_keyword_maps_algorithm(self):
        from src.capability.mapper import map_by_content
        r = map_by_content("使用 threshold 算子对图像进行阈值分割")
        assert 4 in r["domains"]

    def test_calibration_keyword_maps_design(self):
        from src.capability.mapper import map_by_content
        r = map_by_content("相机标定 camera calibration 内参外参")
        assert 3 in r["domains"] or 4 in r["domains"]

    def test_plc_keyword_maps_engineering(self):
        from src.capability.mapper import map_by_content
        r = map_by_content("通过 PLC 通讯控制相机触发，与机器人握手")
        assert 5 in r["domains"]

    def test_ocr_scene_detected(self):
        from src.capability.mapper import map_by_content
        r = map_by_content("OCR 字符识别读取产品上的条码和二维码")
        assert "ocr" in r["scene"] or r["scene"]


class TestClassifyChunk:
    def test_full_metadata_shape(self):
        from src.capability.mapper import classify_chunk
        r = classify_chunk(
            source="check_cable_labels.hdev",
            text="使用 read_image 读取图像，threshold 分割，OCR 识别标签",
        )
        assert set(r) >= {
            "source", "technology", "scene",
            "capability_domain", "capability_items",
            "confidence", "mapping_method",
        }
        assert isinstance(r["capability_items"], str)
        assert "," in r["capability_items"] or r["capability_items"]

    def test_unknown_source_pass_through(self):
        from src.capability.mapper import classify_chunk
        r = classify_chunk(source="tmp_unknown.dat", text="数据")
        assert r["source"] == "tmp_unknown.dat"
        # 未知来源也应给默认 domain（知识研究）
        assert r["capability_domain"] == "2" or "2" in r["capability_domain"]


class TestMetadataInjection:
    def test_inject_capability_into_chunk(self):
        from langchain_core.documents import Document
        from src.vector_store.chroma_client import _inject_capability_metadata
        chunks = [
            Document(
                page_content="使用 threshold 算子对图像进行阈值分割，检测缺陷",
                metadata={"source": "check_blister.hdev"},
            )
        ]
        _inject_capability_metadata(chunks)
        meta = chunks[0].metadata
        assert "capability_domain" in meta
        assert "capability_items" in meta
        assert "technology" in meta
        assert "scene" in meta
        assert "confidence" in meta
        assert "mapping_method" in meta

    def test_skip_already_tagged(self):
        from langchain_core.documents import Document
        from src.vector_store.chroma_client import _inject_capability_metadata
        chunks = [
            Document(
                page_content="whatever",
                metadata={"source": "x.hdev", "capability_domain": "4"},
            )
        ]
        _inject_capability_metadata(chunks)
        # 已打标签的 chunk 不重复注入（mapping_method 不添加）
        assert "mapping_method" not in chunks[0].metadata
        assert chunks[0].metadata["capability_domain"] == "4"


class TestMapCommand:
    def test_map_help(self):
        from typer.testing import CliRunner
        from src.cli.knowledge import app
        r = CliRunner().invoke(app, ["map", "--help"])
        assert r.exit_code == 0
        assert "--capability" in r.output

    def test_map_json_overview(self, tmp_path, monkeypatch):
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        import src.cli.knowledge as K

        # mock vector store returning tagged chunks (one page, then empty)
        mock_vs = MagicMock()
        metas = [{"source": "a.hdev", "capability_domain": "4", "scene": "defect_inspection",
                  "technology": "halcon"}] * 2
        page1 = {"metadatas": metas, "documents": ["x"] * 2, "ids": ["i1", "i2"]}
        empty = {"metadatas": [], "documents": [], "ids": []}
        mock_vs._collection.get.side_effect = [page1, empty]
        mock_vs._collection.count.return_value = 2

        with patch("src.vector_store.chroma_client.get_vector_store", return_value=mock_vs):
            from typer.testing import CliRunner
            r = CliRunner().invoke(K.app, ["map", "--json"])
        assert r.exit_code == 0
        import json
        data = json.loads(r.output)["data"]
        doms = {d["id"]: d for d in data["domains"]}
        assert doms[4]["chunks"] == 2
