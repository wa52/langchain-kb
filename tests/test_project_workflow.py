import pytest


class TestProjectWorkflowStages:
    def test_stages_definition(self):
        from src.agent.project_workflow import PROJECT_STAGES
        assert [s["id"] for s in PROJECT_STAGES] == [1, 2, 3, 4, 5, 6]
        names = [s["name"] for s in PROJECT_STAGES]
        assert names == ["需求分析", "知识研究", "方案设计", "算法实现", "工程开发", "项目验证"]

    def test_stage_has_capability_and_questions(self):
        from src.agent.project_workflow import PROJECT_STAGES
        for s in PROJECT_STAGES:
            assert s["capability"] in (1, 2, 3, 4, 5, 6)
            assert s["questions"], f"{s['name']} 缺引导问题"


class TestProjectWorkflowTool:
    def test_tool_returns_stage_knowledge(self):
        from unittest.mock import patch
        from src.agent.project_workflow import project_workflow

        with patch("src.agent.project_workflow._search_for_stage", return_value=[
            {"source": "a.hdev", "content": "阈值分割知识"}
        ]):
            out = project_workflow.func(project_desc="PCB 表面缺陷检测", stage="方案设计")
        assert "阶段" in out
        assert "3" in out
        assert "a.hdev" in out
        assert "阈值分割知识" in out
        assert "问题" in out

    def test_unknown_stage_returns_guidance(self):
        from src.agent.project_workflow import project_workflow
        out = project_workflow.func(project_desc="x", stage="不存在的阶段")
        # 未知阶段应返回所有阶段列表引导
        assert "需求分析" in out
        assert "项目验证" in out


class TestBuildPrompt:
    def test_workflow_prompt_includes_stages(self):
        from src.agent.project_workflow import build_workflow_prompt
        prompt = build_workflow_prompt()
        assert "工业视觉项目" in prompt
        assert "需求分析" in prompt
        assert "项目验证" in prompt


class TestProjectCommand:
    def test_project_help(self):
        from typer.testing import CliRunner
        from src.cli.knowledge import app
        r = CliRunner().invoke(app, ["project", "--help"])
        assert r.exit_code == 0
        assert "--stage" in r.output

    def test_project_json(self):
        from unittest.mock import patch
        from typer.testing import CliRunner
        from src.cli.knowledge import app

        with patch("src.agent.project_workflow._search_for_stage", return_value=[]):
            r = CliRunner().invoke(app, [
                "project", "PCB 表面缺陷检测", "--stage", "方案设计", "--json",
            ])
        assert r.exit_code == 0
        import json
        data = json.loads(r.output)["data"]
        assert data["project"] == "PCB 表面缺陷检测"
        assert "方案设计" in data["stage"]
        assert "guidance" in data
