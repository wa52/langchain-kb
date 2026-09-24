# Loop 007 — HALCON Evidence-Boundary Harbor Evaluation

## Goal and boundary

Exercise the production Fast RAG answer path on one previously problematic
HALCON `lines_facet` example. The task distinguishes facts visible in example
code from facts requiring operator-reference evidence. It uses only two fixed
synthetic task files: a small HDevelop call and a frozen paraphrase of MVTec
HALCON 24.11.3.0 documentation. No personal knowledge corpus, chat history,
MCP settings, or existing index was read.

The user approved this API-backed task. The answer and grader requests contain
only the task instruction, fixture evidence, and synthetic candidate answers.

## Harness and environment

- Harbor 0.23.0, one attempt, Docker task environment.
- The container policy is `no-network`; its image contains only the two fixture
  files under `/app/evidence/`.
- The custom Harbor Agent downloads only those fixtures and injects them into
  `src.application.fast_rag.FastRagService`; retrieval is replaced with a
  deterministic fixture callback. The configured project's `get_llm()` makes
  the answer-generation call.
- Harbor Agent and verifier launch project Python subprocesses on the host to
  use project dependencies and `.env` configuration. Docker `no-network` only
  fences the task container, not those host subprocesses. This limitation is
  explicit; all transmitted material remains synthetic.
- The semantic verifier is a separate Harbor verifier and makes its own
  configured-model call, using the frozen facts and candidate answer.
- Scan result: none of the configured API key value was found in Harbor job
  artifacts.

## Acceptance and results

Pass iff material claims are supported: `light` means bright-line extraction,
`Lines` is subpixel-precise XLD contours, `lines_facet` extracts line and
curvilinear structures rather than only straight lines, and the answer
distinguishes example-visible facts from reference-backed facts without
inventing undocumented parameter meanings.

| Check | Result |
|---|---:|
| Harbor task config dry-run | PASS; 1 trial resolved |
| Verifier calibration: correct paraphrase | PASS |
| Verifier calibration: plausible wrong claims | FAIL as expected |
| Harbor task | 1/1 completed, 0 errors, reward 1.0 |
| Fast RAG focused regression | 8 passed |
| Full project suite (`kb_env`) | 760 passed, 1 skipped, 3 warnings |
| Personal corpus/history/MCP access | None |

The generated answer correctly stated the bright-line meaning, XLD contour
output, and line/curvilinear scope; it explicitly said the example alone cannot
establish parameter semantics, and marked the other numeric arguments as
unconfirmed. The semantic judge passed it.

## Timing

Captured from `FastRagPlan.snapshot()` in the Harbor answer artifact:

| Stage | Duration |
|---|---:|
| Retrieval fixture callback | 0.00 ms |
| Relevance gate | 0.09 ms |
| Context build | 0.10 ms |
| Model streaming (1 call) | 8760.03 ms |
| Fast RAG total | 8760.22 ms |

For this bounded task, nearly all answer latency came from the model call, not
RAG file scanning or context preparation. The fixture callback is intentionally
constant-time and is not a production retrieval benchmark.

## Reproducibility

- Task: `evals/halcon-lines-facet-evidence/`
- Job: `evals/jobs/loop007-halcon-fast-rag-evidence/`
- Verifier calibration: `evals/harbor_agents/calibration.json`
- Official reference: [MVTec HALCON 24.11 `lines_facet` operator reference](https://www.mvtec.com/doc/halcon/2411/en/lines_facet.html)
- Harness SHA-256:
  - `production_fast_rag.py`: `1B17C6390545B9BA5FFEBD0A899C47896E8CD871E234628D94A9C313117D2004`
  - `fast_rag_worker.py`: `3C5623D0653694AA617DF393882C6F0EB2FF8DF7EDF287C861684F319F5D40E7`
  - `fast_rag_verifier.py`: `2D3259119E0676E7AA2DEBBBF95F0DE7D1B2BC965CE3AEA906956499F50750E0`
- Task checksum is also recorded in Harbor's job lock.

The global Python has MCP SDK 2.2.0, outside the repository's `mcp>=1.12.0,<1.28.0`
constraint; invoking the full suite there caused collection errors. Running the
complete suite in the project `kb_env` with its declared dependency set passed.

## Limitation / next gap

One passed task demonstrates this case works; it does not establish general
answer groundedness or prove retrieval quality on the real corpus. The next
answer-evaluation loop should add a small, independently reviewed synthetic
benchmark with supported, contradicted, and insufficient-evidence cases before
making broad product-quality claims.
