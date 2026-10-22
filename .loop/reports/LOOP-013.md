# Loop 013 — Tracked Source Reindex Identity

The old Knowledge-page action submitted a tracker-relative key to the generic
add/import endpoint. Nested files could be looked up under the process CWD or
copied as new external sources. The former single-file update also wrote a
basename source key and lost nested provenance on Windows.

The new `POST /api/v1/files/reindex` accepts `{source_type, file_key}`. It
requires an exact tracker entry under the configured internal/external root,
rejects path escapes and cross-root source-key collisions, and runs an async
replacement task. Ingestion loads exactly that file, writes the normalized
full source key, removes both normalized and legacy Windows source spellings,
updates the matching tracker root, and preserves the previous index if
parsing returns no documents. The Web action uses this endpoint, not the
generic add path. The changed row controls use recognizable refresh/remove
icons, keyboard labels, and delayed Chinese hover hints.

## Verification

- Red test: new reindex route returned 405; the focused test then passed after
  implementation. A pipeline test caught the Windows slash mismatch before
  normalization and passed after the fix.
- Focused file API and consistency tests: 17 passed.
- Full suite under synthetic `KNOWLEDGE_HOME` and empty scheduled sources:
  801 passed, 1 skipped, 3 warnings.
- Web typecheck and production build passed; `git diff --check` passed.
- Real Chrome/Vite render with a synthetic two-file API: 890px desktop and
  390px narrow viewport showed both row actions and a long nested path without
  clipping or document-level horizontal overflow. No reindex/remove action was
  clicked. Temporary QA servers were stopped.
- Visual self-review (1–5): coordination 4, hierarchy 4, typography 4,
  components 4, space use 4, interaction clarity 4, completeness 4 for this
  changed row. Hover timing is defined at 1.5s in CSS; actual pointer-hover
  timing was not instrumented by the available browser control.

## Remaining limits

Only internal/external tracked files use this reindex API; experience sources
continue through scheduled sync. The existing remove-by-basename path can
affect multiple same-named files and needs its own identity-safe iteration.
No production source files were deliberately indexed or removed. A legacy
lifespan test unexpectedly began scheduled sync before being stopped; this is
recorded as `FAIL-0010`, and production index integrity needs owner direction.
