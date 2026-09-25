"""Harbor adapter for a single Fast RAG turn over Docker task fixtures."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from harbor.agents.base import BaseAgent
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext


ROOT = Path(__file__).resolve().parents[2]
WORKER = ROOT / "evals" / "harbor_agents" / "fast_rag_worker.py"
PYTHON = ROOT / "kb_env" / "Scripts" / "python.exe"
FIXTURES = (
    ("/app/evidence/lines_facet_example.hdev", "lines_facet_example.hdev"),
    ("/app/evidence/lines_facet_reference.md", "lines_facet_reference.md"),
)


class ProductionFastRagAgent(BaseAgent):
    fixtures = FIXTURES

    @staticmethod
    def name() -> str:
        return "production-fast-rag"

    def version(self) -> str:
        return "1.0"

    async def setup(self, environment: BaseEnvironment) -> None:
        return None

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        documents = []
        with tempfile.TemporaryDirectory(prefix="harbor-halcon-") as temp_dir:
            temp = Path(temp_dir)
            for remote, source in self.fixtures:
                local = temp / source
                await environment.download_file(remote, local)
                documents.append({"source": source, "text": local.read_text(encoding="utf-8")})
            input_path = temp / "input.json"
            output_path = self.logs_dir / "fast_rag_result.json"
            input_path.write_text(
                json.dumps({"question": instruction, "documents": documents}, ensure_ascii=False),
                encoding="utf-8",
            )
            completed = subprocess.run(
                [str(PYTHON), str(WORKER), "answer", str(input_path), str(output_path)],
                cwd=ROOT,
                capture_output=True,
                text=True,
                timeout=150,
                check=False,
            )
            if completed.returncode:
                self.logger.error("Fast RAG worker failed (exit=%s)", completed.returncode)
                raise RuntimeError("Fast RAG worker failed; see sanitized worker status")
            result = json.loads(output_path.read_text(encoding="utf-8"))
            context.metadata = {
                "answer_path": str(output_path),
                "route": "FastRagService",
                "fixture_sources": [item["source"] for item in documents],
                "plan": result.get("plan", {}),
            }
