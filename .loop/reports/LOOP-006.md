# Loop 006 — Tool Selection Evaluation Runner

## Delivered

- Added 11 versioned synthetic cases over knowledge search, graph search,
  project workflow, external reads, and external writes.
- Added a deterministic evaluator using the production `RuleBasedToolSelector`
  seam and the production `JevToolSelector` with an injected offline request
  stub. The stub ranks by query/description token overlap and does not inspect
  expected labels.
- Added a hash-pinned report with separate Rule and Jev-simulation metrics,
  provider mode, per-case rank, write-tool false exposure, selector latency,
  and an explicit offline/no-external-provider marker.
- Added `GET /api/v1/evaluations/tools/latest` with a typed response model that
  filters unexpected report fields. The Evaluation page has loading, empty,
  error, and completed states, and compares both result sets.
- No production selector, Agent, chat, SSE, MCP configuration, or RAG corpus
  behavior was changed.

## Safety boundary

Only repository-owned fake tools and synthetic queries were evaluated. The
runner ignores any configured `TYPESAFE_API_KEY`, invokes no network client,
does not read the user corpus or chat history, and stores no key or query text
in the report. `external_provider_called` is fixed to `false` and the API
rejects reports that claim otherwise.

The Jev result is a deterministic adapter simulation, **not a real Jev model
evaluation**. It validates adapter and reporting integration only. A real
quality comparison requires a separately approved network-enabled run.

## Results

Dataset SHA-256: `6145d1a3a398faf20bffef0d7127d19a5487aa1fde670cea8c89872a1142a148`

| Mode | Top-1 | Top-3 | Write false exposure | P50 / P95 selector time |
|---|---:|---:|---:|---:|
| Rule baseline | 100.0% | 100.0% | 0.0% | 0.023 / 0.652 ms |
| Jev adapter simulation | 27.3% | 72.7% | 0.0% | 0.055 / 0.084 ms |

These scores only describe this small synthetic dataset and the local stub; do
not generalize them to user traffic or real Jev.

## Verification

- `kb_env\\Scripts\\python.exe -m evals.tools.run` — passed; wrote the
  versioned report to `evals/tools/reports/latest.json`.
- Focused API and evaluator tests — 38 passed before the final report schema
  hardening; final full suite below includes the updated API schema tests.
- `kb_env\\Scripts\\python.exe -m pytest tests/ -q -p no:cacheprovider` —
  760 passed, 1 skipped, 3 pre-existing deprecation warnings.
- `npm run typecheck` and `npm run build` — passed.
- Browser check on the Evaluation page — both modes, per-case rows, and the
  simulation disclaimer rendered from the generated report.
- `git diff --check` — passed (Git emitted only repository line-ending notices).
