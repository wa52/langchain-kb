"""Independent semantic verifier for the synthetic HALCON evidence task."""

from __future__ import annotations

import asyncio
import json
import subprocess
import tempfile
from pathlib import Path

from harbor.models.verifier.result import VerifierResult
from harbor.verifier.base import BaseVerifier

from evals.harbor_agents.production_fast_rag import PYTHON, ROOT, WORKER


EVIDENCE = """HALCON 24.11.3.0 operator reference (paraphrase): lines_facet extracts line and curvilinear structures; output Lines is a subpixel-precise XLD contour object; LightDark selects bright or dark lines, with documented values `light` and `dark`. The synthetic HDevelop example visibly calls lines_facet(..., 'light'); by itself that code only proves the call and literal shown, not the output type or undocumented parameter semantics. Source: https://www.mvtec.com/doc/halcon/2411/en/lines_facet.html"""
QUESTION = "解释 lines_facet 示例中 LightDark 的含义、Lines 输出类型及算子用途，并区分示例与手册证据。"


class FastRagSemanticVerifier(BaseVerifier):
    async def verify(self) -> VerifierResult:
        answer_path = self.trial_paths.agent_dir / "fast_rag_result.json"
        if not answer_path.is_file():
            raise RuntimeError("Fast RAG answer artifact is missing")
        answer = json.loads(answer_path.read_text(encoding="utf-8")).get("answer", "")
        with tempfile.TemporaryDirectory(prefix="harbor-halcon-judge-") as temp_dir:
            source = Path(temp_dir) / "judge_input.json"
            target = Path(temp_dir) / "judge_output.json"
            source.write_text(
                json.dumps({"question": QUESTION, "evidence": EVIDENCE, "answer": answer}, ensure_ascii=False),
                encoding="utf-8",
            )
            completed = await asyncio.to_thread(
                subprocess.run,
                [str(PYTHON), str(WORKER), "judge", str(source), str(target)],
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
            "criterion": "HALCON semantic grounding and example/reference evidence boundary",
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
