"""Semantic verifier for unsupported HALCON operator-detail abstention."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from harbor.models.verifier.result import VerifierResult
from harbor.verifier.base import BaseVerifier

from evals.harbor_agents.production_fast_rag import PYTHON, ROOT, WORKER


QUESTION = (
    "请解释 lines_facet 调用中 5、3、5 和 'light' 分别表示什么，"
    "并说明 Lines 输出类型及算子提取的结构。请基于知识库资料回答并标注来源。"
)
EVIDENCE = """唯一资料是 HDevelop 示例 lines_facet_example.hdev：
read_image (Image, 'sample_image')
dev_set_colored (6)
lines_facet (Image, Lines, 5, 3, 5, 'light')
该代码只展示调用位置、变量和传入字面值；没有算子手册或参数说明。"""


class FastRagExampleOnlyVerifier(BaseVerifier):
    async def verify(self) -> VerifierResult:
        answer_path = self.trial_paths.agent_dir / "fast_rag_result.json"
        if not answer_path.is_file():
            raise RuntimeError("Fast RAG answer artifact is missing")
        answer = json.loads(answer_path.read_text(encoding="utf-8")).get("answer", "")
        with tempfile.TemporaryDirectory(prefix="harbor-halcon-abstention-") as temp_dir:
            source = Path(temp_dir) / "judge_input.json"
            target = Path(temp_dir) / "judge_output.json"
            source.write_text(
                json.dumps({"question": QUESTION, "evidence": EVIDENCE, "answer": answer}, ensure_ascii=False),
                encoding="utf-8",
            )
            completed = await asyncio.to_thread(
                subprocess.run,
                [str(PYTHON), str(WORKER), "judge-example-only", str(source), str(target)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=150,
                check=False,
            )
            if completed.returncode:
                raise RuntimeError("semantic judge infrastructure failed")
            verdict = json.loads(target.read_text(encoding="utf-8"))
        report = {
            "criterion": "abstain from unsupported HALCON operator details when only an example is available",
            "pass": verdict["pass"],
            "reason": verdict["reason"],
            "answer": answer,
            "judge_model": "configured project model",
        }
        (self.trial_paths.verifier_dir / "semantic_verdict.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        self.logger.info("Semantic verdict: %s — %s", "PASS" if verdict["pass"] else "FAIL", verdict["reason"])
        return VerifierResult(rewards={"reward": 1 if verdict["pass"] else 0})
