# Loop 014 — Exact Tracked Source Removal

## Delivered

The Knowledge page's remove action now calls `POST /api/v1/files/remove` with
`source_type` and the full tracked `file_key`. The API validates the exact
tracker identity, rejects path traversal and cross-source index collisions,
and schedules one operation for that source. The original disk file is kept.
The Web confirmation and delayed Chinese tooltip state that behavior.

The ingestion operation removes only the matching vector source (including
legacy Windows separator provenance), rebuilds BM25 and the optional graph,
then removes the exact tracker record. A failure restores prior vector and
tracker state. Remove and reindex share a task key to prevent concurrent
operations against the same source. The ingestion layer does not import API
code.

## Verification

- Focused file/API and consistency regressions: 26 passed.
- Isolated full suite in `kb_env`: 810 passed, 1 skipped, 3 warnings.
- Web `npm run typecheck` and `npm run build`: passed.
- Python changed-file compilation and `git diff --check`: passed.
- Real isolated Web instance on port 18002 rendered an empty Knowledge page and
  two synthetic nested sources with the same basename. Desktop (1280px) and
  narrow (390px) screenshots showed readable full keys and separate icon
  actions with no observed clipping or overlap. Buttons exposed distinct
  accessible names; CSS retains the 1.5-second Chinese hint delay. The
  destructive confirmation was not clicked, so visual post-removal behavior
  was not exercised.
- All mutation tests used a synthetic `KNOWLEDGE_HOME`; no production source
  was removed, hashed, or reindexed.

## Limitations

The legacy basename `DELETE /api/v1/files/{name}` endpoint remains available
for compatibility and can still be ambiguous for nested duplicate names. It
is not used by the Knowledge page. Existing production index integrity work
is tracked separately in `FAIL-0010` and `BLOCKED_REPORT.md`.
