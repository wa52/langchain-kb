# Acceptance Contract

These are product gates, not aspirations. Numeric thresholds become enforced
only after a reproducible baseline corpus and runner exist; until then their
status remains `UNBASELINED` rather than being silently claimed.

## Engineering gates for every loop

- Focused unit and integration tests for the changed seam pass.
- Existing relevant regression tests pass.
- Web typecheck and production build pass when the Web client changes.
- No new circular dependency; application code does not import a concrete
  adapter directly.
- New backend capability has REST coverage and a UI path when it is a user
  feature.
- Builder does not lower thresholds, delete a failing test, or rewrite golden
  data to fit its implementation without an approved recorded decision.

## Product quality targets

| Domain | Gate | Target | Status |
|---|---|---:|---|
| Retrieval | Recall@5 | >= 0.90 | UNBASELINED — the 4-document/8-chunk fixture saturates at K=5 and is not representative |
| Retrieval | MRR | >= 0.80 | UNBASELINED — fixture MRR 0.8929 is smoke evidence only |
| Retrieval | P95 search | < 500 ms | UNBASELINED — fixture P95 21.79 ms excludes production corpus/startup conditions |
| Knowledge | Health audit coverage | 100% of tracker snapshot entries classified; hash/content data never returned; no automatic page-load scan | BASELINED — synthetic internal/external/experience roots and safety boundaries |
| Routing | Macro F1 | >= 0.90 | BASELINED (current test gate is >= 0.98) |
| Routing | Side-effect agent recall | 1.00 | UNBASELINED |
| Answer | Citation correctness | >= 0.95 | UNBASELINED — two focused HALCON Harbor cases pass; insufficient corpus breadth for this gate |
| Answer | Unsupported-claim rate | <= 0.05 | UNBASELINED — example-only abstention is covered, but a representative multi-domain dataset is still missing |
| Tools | Top-3 recall | >= 0.95 | UNBASELINED — synthetic Rule/Jev-adapter smoke data only; configured Vercel Gateway currently rejects real Jev calls with HTTP 403 |
| Tools | Write false exposure | <= 0.01 | UNBASELINED — synthetic smoke data only; real Jev comparison awaits Gateway authorization |
| Performance | Fast RAG TTFT | < 2 s | UNBASELINED |
| Performance | Fast RAG P95 | < 6 s | UNBASELINED |
| Performance | Router P95 overhead | < 500 ms | UNBASELINED |

## Stop conditions

Stop and produce `BLOCKED_REPORT.md` instead of looping when the same test or
metric fails three times without improvement, a destructive migration is
needed, a core architectural rule must change, a real secret/permission is
needed, a security issue is found, or a human product decision is required.
