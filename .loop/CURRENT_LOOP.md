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

## Boundary and result

The approved scope uses synthetic task data only, the production `FastRagService`
and configured project LLM API, plus a separately invoked semantic verifier.
The Docker task environment is configured without network access and contains
only frozen synthetic example/reference files. The Harbor host-side adapter
downloads just those fixtures and makes the approved model calls from the host;
therefore the Docker network policy does not constrain the host-side calls.
No personal corpus, chat history, or MCP configuration is accessed. See
`reports/LOOP-007.md`, the Harbor job under `evals/jobs/`, and the verifier
calibration at `evals/harbor_agents/calibration.json`. Result: 1/1 reward 1.0;
full regression in `kb_env`: 760 passed, 1 skipped.
