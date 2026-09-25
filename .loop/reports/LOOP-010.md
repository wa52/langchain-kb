# Loop 010 — On-Demand Knowledge Source Health

## Result

Delivered an on-demand, asynchronous audit of files already recorded by the
file tracker. The audit covers internal, external, and configured experience
roots; classifies each tracked item; and compares current SHA-256 with the
tracker fingerprint to detect changes and duplicates.

The audit is opt-in: opening the Knowledge page or listing files does not read
or hash files. Only exact tracked paths are checked. Paths are resolved against
their configured root to reject traversal and symlink escapes. API responses
contain relative labels and status summaries only—not file contents, hashes, or
absolute paths. At most one task may run at a time, and task progress/results
are retained in a bounded in-memory store.

The Knowledge page now has an explicit health-check action, progress display,
summary counts, issue details, and error/empty states.

## Verification

- Focused source-health, file API, and OpenAPI tests: 12 passed, 1 skipped.
  The skipped test requires creating a symlink, which this Windows host does
  not permit for the current user.
- Full project test suite in `kb_env`: 783 passed, 2 skipped, 3 warnings.
- Web `npm run build` (includes `tsc --noEmit`): passed.
- `git diff --check`: passed.
- Running service `/api/v1/health`: `status=ok`.
- Running service OpenAPI: both start and poll endpoints are present.
- Running service `/`: references the current built JS/CSS bundle.
- Synthetic API/service tests cover start, poll, progress, and no implicit scan
  on ordinary file listing.

The real user corpus was not scanned. The live UI audit button was not clicked,
because that would read and hash real tracked files; live rendered result-state
interaction is therefore not claimed as verified.

## Follow-up gaps

- Knowledge source add/remove/refresh lifecycle and source health beyond the
  tracker snapshot are still incomplete.
- The audit task store is process-local/in-memory and resets on service restart.
- A real-corpus audit and browser interaction require explicit user intent.
