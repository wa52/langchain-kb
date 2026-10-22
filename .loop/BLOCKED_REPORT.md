# External Blocker — Real Jev Tool-Selection Evaluation

## Blocked acceptance

The configured Vercel AI Gateway credential reaches the documented Jev
TypeSafe-compatible endpoint, but the Gateway returns HTTP 403 for a synthetic
tool-choice request. The old direct TypeSafe host returned HTTP 401 for this
Gateway key. The provider-routing bug is fixed; the remaining rejection is
outside this repository.

## Evidence and impact

- The explicit Web Settings connection test displays `Vercel AI Gateway` and
  HTTP 403, without exposing the key or response body.
- Agent requests safely fall back to deterministic rules; repeated rejected
  calls are suppressed in the current process.
- A real Jev quality or latency benchmark cannot be run. Top-3 recall and
  write-tool exposure remain `UNBASELINED`; the local Jev simulation is not
  counted as model evidence.

## Unblock condition

Gateway access must accept a synthetic Jev request with the existing or a
replacement authorized Gateway key. The user can press **测试连接** on the
Settings page; a `ready` result confirms the external blocker has cleared.
The explicit check reprobes even after a previous 403, and replacing the key
also clears the process's rejected-key state. No user corpus is needed for the
subsequent tool-selection evaluation.

This blocker applies to the real Jev benchmark. Independent knowledge,
retrieval, answer, lifecycle, and UI acceptance gaps remain open.

## Production index integrity — needs owner direction

During Loop 013, the pre-existing source-health TestClient lifecycle test
unexpectedly triggered scheduled experience sync. The process was stopped
after it loaded documents and the embedding model. Read-only timestamps show
`chroma.sqlite3` and the BM25 invalidation marker were updated, while the
tracker, graph, and sync-status files retained older timestamps. A subsequent
read-only SQLite `PRAGMA quick_check` reported `malformed inverted index for
FTS5 table main.embedding_fulltext_search`. There is no pre-run integrity
baseline, so the cause and scope cannot be attributed with certainty.

The test is now isolated and the entire suite passes against a synthetic
`KNOWLEDGE_HOME`. No production rebuild, FTS repair, or rollback has been
attempted. Before release acceptance or further production-data testing, the
owner should choose a recoverable backup-and-repair procedure; changes to the
real index require explicit direction.
