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
