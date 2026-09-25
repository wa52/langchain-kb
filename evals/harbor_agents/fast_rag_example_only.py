"""Production Fast RAG adapter for a code-example-only evidence environment."""

from evals.harbor_agents.production_fast_rag import ProductionFastRagAgent


class ProductionFastRagExampleOnlyAgent(ProductionFastRagAgent):
    fixtures = (("/app/evidence/lines_facet_example.hdev", "lines_facet_example.hdev"),)

    @staticmethod
    def name() -> str:
        return "production-fast-rag-example-only"

    def version(self) -> str:
        return "1.0"
