# Loop 008 — Scoped Local Filesystem Capability

## Goal

Allow the Agent to inspect and compare explicitly authorized local folders, and
index user-selected documents through the existing duplicate-aware ingestion
pipeline. Prevent the assistant from claiming filesystem access when the
filesystem capability is unavailable.

## Acceptance

- [x] Filesystem requests route to Agent/filesystem; conceptual/how-to questions
      stay on the direct path.
- [x] Read/compare tool only returns supported file names and hash duplicate
      matches; file contents are not returned.
- [x] Both tools reject paths outside enabled filesystem MCP configured roots;
      symlink escapes are excluded.
- [x] Index tool uses existing ingestion, dedupes against every tracked source,
      invalidates retrieval caches on successful changes, and requires approval.
- [x] Capability catalog API lists both tools with read/write and risk metadata;
      generic Capabilities UI consumes that API.
- [x] Focused, API, and full regression suites pass; no user directory is scanned
      during tests.

## Scope guard

Do not enumerate, read, hash, or index any real user directory as part of
verification. Synthetic temporary fixtures only. Do not broaden the existing
filesystem roots; the one additional root is the exact HALCON examples folder
named by the user's screenshot. No credentials or document contents go in API
or capability metadata.

## Status

DONE. Last full regression: 773 passed, 1 skipped. See `reports/LOOP-008.md`.

# Loop 009 — Preserve Filesystem Tool Context in Follow-ups

## Goal

Prevent a short follow-up after an explicit local-file task from being routed
to the tool-less Direct model, which caused a false “cannot access local files”
answer.

## Acceptance

- [x] A recent explicit filesystem task followed by an access-failure question
      routes to Agent with `domain=filesystem` and no write side effect.
- [x] The resulting selection context exposes `inspect_local_path`.
- [x] Without a recent filesystem task, the same short question stays Direct.
- [x] Agent instructions require using the real tool result instead of a generic
      access disclaimer; importing remains approval-gated.
- [x] Full regression suite passes; no user file contents were read or hashed.

## Verification

The regression test was observed failing before the fix. Focused filesystem,
routing, and runtime tests passed (39 passed); full suite passed (775 passed,
1 skipped). The configured target path was checked only for existence and
allowlist membership. The live API reloaded the Python changes automatically.

## Status

DONE. See `reports/LOOP-009.md`.

# Loop 010 — On-Demand Knowledge Source Health

## Goal

Expose an explicit, safe health audit for already-indexed knowledge sources so
users can find missing, changed, duplicate, inaccessible, or unresolved files.
Opening the Knowledge page must not start a filesystem scan.

## Acceptance

- [x] Classify every tracker snapshot entry across configured internal,
      external, and experience roots.
- [x] Hash only the exact tracked file under its configured root; reject
      traversal and symlink escapes.
- [x] Do not return document content, file hashes, or absolute root paths.
- [x] Start the audit only through an explicit API/UI action; run it off the
      FastAPI event loop, expose progress, and prevent duplicate concurrent
      audits.
- [x] Add Knowledge-page progress, result, empty, and error states.
- [x] Focused and full tests pass; Web typecheck/build pass; exercise the new
      routes on the running service.

## Scope guard

Do not start a health audit against the real user corpus. Verification uses
synthetic files only; real tracked files are not read or hashed.

## Verification

Focused tests: 12 passed, 1 skipped (Windows host does not grant symlink
creation permission). Full suite: 783 passed, 2 skipped, 3 warnings. Web
typecheck/build passed. `git diff --check` passed. Running service health
endpoint returned `ok`; its OpenAPI exposed both health-audit routes and its
root page referenced the current production bundle. Synthetic service/API
tests exercised task creation and polling. The UI action was not clicked to
avoid reading/hashing the user's real tracked documents, so live rendered
result-state interaction remains unverified.

## Status

DONE. See `reports/LOOP-010.md`.
