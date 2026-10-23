# Loop 015 — Fail-Closed Legacy Removal

## Delivered

The old basename-only `run_remove` path is still available to CLI, MCP, and
the compatibility API. It now accepts only a single tracked external source
whose key is a flat file name. It rejects a nested or duplicate name before
touching the vector index, and it cannot delete a matching directory or
symlink. The API description explains the restriction and directs clients to
the exact-source endpoint.

The unique source's vector index, BM25, optional graph, and tracker record are
updated with rollback on failure. The disk file is unlinked only after those
steps succeed, unless `keep_file` is set.

## Verification

- Synthetic duplicate-basename rejection, directory rejection, unique-file
  removal, and BM25-failure rollback tests passed.
- Isolated full suite in `kb_env`: 814 passed, 1 skipped, 3 warnings.
- Changed Python files compiled and `git diff --check` passed.
- No real user source was removed or tested through the compatibility endpoint.

## Limits

The compatibility API still starts an asynchronous task before worker-side
validation, so unsafe requests receive a failed task status rather than an
immediate HTTP 400. Disk unlink failure after a successful index change leaves
the original file on disk, ready for explicit reindexing or manual cleanup.
