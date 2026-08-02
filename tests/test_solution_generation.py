import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


class TestRequirementAnalyzer:
    def test_analyze_pcb(self):
        from src.agent.requirement_analyzer import analyze_requirement

        fake_llm = MagicMock()
        fake_llm.invoke.return_value.content = json.dumps({
            "product": "PCB",
            "task": "缺陷检测",
            "target": "划痕、异物、缺件",
            "precision": "0.1mm",
            "speed": "未明确",
            "environment": "未明确",
        }, ensure_ascii=False)

        r = analyze_requirement("设计一个PCB缺陷检测系统", fake_llm)
        assert r["product"] == "PCB"
        assert r["task"] == "缺陷检测"
        assert isinstance(r["unknown"], list)

    def test_analyze_fallback_on_bad_llm(self):
        from src.agent.requirement_analyzer import analyze_requirement
        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("api down")
        r = analyze_requirement("设计一个测量系统", fake_llm)
        assert "product" in r
        assert "task" in r


class TestAlgorithmSelector:
    def test_rules_measurement(self):
        from src.agent.algorithm_selector import select_algorithm
        r = select_algorithm("测量", "measurement", llm=None)
        assert "边缘" in " ".join(r["algorithms"]) or "卡尺" in " ".join(r["algorithms"])

    def test_rules_defect(self):
        from src.agent.algorithm_selector import select_algorithm
        r = select_algorithm("缺陷检测", "defect_inspection", llm=None)
        assert any(a in " ".join(r["algorithms"]) for a in ["Blob", "分割", "异常"])

    def test_rules_ocr(self):
        from src.agent.algorithm_selector import select_algorithm
        r = select_algorithm("OCR", "ocr", llm=None)
        assert any(a in " ".join(r["algorithms"]) for a in ["OCR", "条码"])

    def test_unknown_task(self):
        from src.agent.algorithm_selector import select_algorithm
        r = select_algorithm("未知任务", "", llm=None)
        assert r["task"] == "未知任务"
        assert r["algorithms"]


class TestSelectAlgorithmLlm:
    def test_llm_refines_operators(self):
        import json
        from unittest.mock import MagicMock, patch
        from src.agent.algorithm_selector import select_algorithm_llm

        fake_llm = MagicMock()
        fake_llm.invoke.return_value.content = json.dumps({
            "operators": ["threshold", "connection", "select_shape"],
            "refinements": "低对比度缺陷建议先做形态学开运算增强",
        }, ensure_ascii=False)

        with patch("src.agent.algorithm_selector._search_capability",
                   return_value=[{"source": "a.hdev", "content": "threshold"}]):
            r = select_algorithm_llm("缺陷检测", "defect_inspection", fake_llm)

        assert r["llm_refinements"]  # 含 LLM 细化建议
        assert "threshold" in str(r.get("operators", []))

    def test_llm_failure_keeps_rules(self):
        from unittest.mock import MagicMock, patch
        from src.agent.algorithm_selector import select_algorithm_llm

        fake_llm = MagicMock()
        fake_llm.invoke.side_effect = RuntimeError("api down")

        with patch("src.agent.algorithm_selector._search_capability", return_value=[]):
            r = select_algorithm_llm("缺陷检测", "defect_inspection", fake_llm)

        # LLM 失败时保留规则表算法
        assert any(a in " ".join(r["algorithms"]) for a in ["Blob", "分割", "异常"])
        assert r["llm_refinements"] == ""


class TestSolutionGenerator:
    def test_generate_structure(self):
        from src.agent.solution_generator import generate_solution

        requirement = {
            "product": "PCB", "task": "缺陷检测",
            "target": "划痕", "precision": "0.1mm",
            "speed": "", "environment": "", "unknown": [],
        }
        algorithm = {"task": "缺陷检测", "algorithms": ["Blob分析"], "reason": "区域特征"}

        fake_llm = MagicMock()
        fake_llm.invoke.return_value.content = "这是生成的方案内容"

        with patch("src.agent.solution_generator._search_capability",
                   return_value=[{"source": "a.hdev", "content": "阈值分割"}]):
            sol = generate_solution(requirement, algorithm, fake_llm)

        assert isinstance(sol, dict)
        assert "sections" in sol or "requirement" in sol
        # 方案应包含关键节
        text = json.dumps(sol, ensure_ascii=False)
        assert "需求分析" in text or "检测目标" in text

    def test_capability_search_called(self):
        from src.agent.solution_generator import generate_solution
        requirement = {"product": "PCB", "task": "缺陷", "target": "", "precision": "",
                       "speed": "", "environment": "", "unknown": []}
        algorithm = {"task": "缺陷", "algorithms": ["Blob"], "reason": "x"}
        fake_llm = MagicMock()
        fake_llm.invoke.return_value.content = "方案"
        with patch("src.agent.solution_generator._search_capability") as m:
            m.return_value = []
            generate_solution(requirement, algorithm, fake_llm)
            caps = [c.args[0] for c in m.call_args_list]
            assert 1 in caps and 3 in caps and 4 in caps
            assert 5 in caps and 6 in caps


class TestProjectReport:
    def test_write_report_files(self, tmp_path):
        from src.agent.project_report import write_report
        sections = {
            "requirement": "# 需求分析\n内容",
            "solution": "# 方案\n内容",
            "algorithm": "# 算法\n内容",
            "risk": "# 风险\n内容",
            "questions": "# 问题\n内容",
        }
        out = write_report(tmp_path, sections)
        assert (tmp_path / "requirement.md").exists()
        assert (tmp_path / "solution.md").exists()
        assert (tmp_path / "algorithm.md").exists()
        assert (tmp_path / "risk.md").exists()
        assert (tmp_path / "questions.md").exists()
        assert out == sorted(out)


class TestDesignCli:
    def test_design_help(self):
        from typer.testing import CliRunner
        from src.cli.knowledge import app
        r = CliRunner().invoke(app, ["design", "--help"])
        assert r.exit_code == 0
        assert "--llm-check" in r.output

    def test_design_uses_llm_algorithm_selector(self, tmp_path, monkeypatch):
        """design 应调用 select_algorithm_llm（而非纯规则 select_algorithm），
        并把 LLM 细化写入 algorithm.md"""
        import json
        from unittest.mock import MagicMock, patch
        from typer.testing import CliRunner
        from src.cli.knowledge import app

        monkeypatch.setattr("config.KNOWLEDGE_HOME", tmp_path)

        fake_llm = MagicMock()
        # requirement 解析返回
        fake_llm.invoke.side_effect = [
            MagicMock(content=json.dumps(
                {"product": "PCB", "task": "缺陷检测", "target": "划痕",
                 "precision": "", "speed": "", "environment": "", "unknown": []},
                ensure_ascii=False)),
            # 方案生成
            MagicMock(content="方案内容"),
        ]

        # 关键：patch select_algorithm_llm 验证它被调用
        with (
            patch("src.llm.get_llm", return_value=fake_llm),
            patch("src.agent.algorithm_selector.select_algorithm_llm") as m_alg,
            patch("src.agent.requirement_analyzer.analyze_requirement",
                  return_value={"product": "PCB", "task": "缺陷检测", "target": "划痕",
                                "precision": "", "speed": "", "environment": "", "unknown": []}),
            patch("src.agent.solution_generator.generate_solution",
                  return_value={"sections": [{"key": "risk", "title": "风险", "content": "x"},
                                             {"key": "questions", "title": "问题", "content": "y"}]}),
        ):
            m_alg.return_value = {
                "task": "缺陷检测", "algorithms": ["Blob分析"], "reason": "区域特征",
                "operators": ["threshold", "connection"],
                "llm_refinements": "建议加形态学开运算", "knowledge_refs": [],
            }
            r = CliRunner().invoke(app, [
                "design", "PCB缺陷检测", "--json",
            ])

        assert r.exit_code == 0
        # 验证 select_algorithm_llm 被调用（且传了 llm 而非 None）
        assert m_alg.called
        _, kwargs = m_alg.call_args
        assert kwargs.get("llm") is fake_llm

        # 验证 algorithm.md 包含 LLM 细化
        alg_file = tmp_path / "data" / "projects" / "PCB缺陷检测" / "algorithm.md"
        assert alg_file.exists()
        text = alg_file.read_text(encoding="utf-8")
        assert "threshold" in text
        assert "形态学" in text
