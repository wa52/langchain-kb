# Production index integrity — backup and read-only diagnosis

## Scope and preservation

The owner authorized a recoverable snapshot and read-only diagnosis, not an
index repair or rebuild. No service was stopped and no production-index write
was deliberately made during this investigation. No Python service process or
listener on ports 8000, 18000, or 18001 was observed; Windows CIM process
enumeration was unavailable, so this does not prove that no other writer
existed.

The local snapshot is `.tmp/production-index-backup-20261022-01/` (excluded
from Git). It contains all seven files in `chroma_db/` and four companion
files: `data/file_tracker.json`, `data/knowledge_graph.gpickle`,
`data/knowledge_graph.json`, and `data/sync_status.json`. Total size:
1,136,741,205 bytes. All 11 copied files had the same length and SHA-256
hash as their source. The source `chroma.sqlite3` modification time remained
2026-10-22 12:36:27 during the investigation. The snapshot does not include
document originals, chat history, credentials, or every file in `data/`.
It can restore the observed bytes, but it is **not a healthy-state backup**.

## Reproducible failure signal

With Python 3.13's SQLite 3.50.4, open the snapshot SQLite file using a
`mode=ro` URI and run `PRAGMA quick_check`. It reproducibly returns:

```text
malformed inverted index for FTS5 table main.embedding_fulltext_search
```

`PRAGMA integrity_check` returns the same result. The FTS table is an
internal-content `fts5(string_value, tokenize='trigram')` virtual table.
It has 151,062 rows, equal to the `embeddings` row count; equal counts do
not establish index/content consistency. A limited `MATCH 'hal'` lookup
returned one row ID, but does not establish complete or correct search.

Targeted `PRAGMA integrity_check` checks of `embeddings`,
`embedding_metadata`, `embedding_fulltext_search_content`, and
`embedding_fulltext_search_data` each returned `ok`. This narrows the
observed error to FTS5's virtual-table integrity path; it does not prove
that all non-FTS data or the HNSW index is healthy. ChromaDB 1.5.9 is
installed in the global test Python environment. No live Chroma client was
opened, because initialization could write to the production index.

## Interpretation and next gate

SQLite's virtual-table integrity hook is invoked by the PRAGMA checks, and
FTS5 checks both its inverted structure and its internal content. The
read-only evidence cannot distinguish a broken inverted structure from an
index/content mismatch. The absence of a pre-incident integrity baseline
also prevents attributing this state to the earlier test run.

The incident remains **open**. Do not run FTS `rebuild`, Chroma reset,
ingestion, or automatic repair on the production index. Before seeking
approval for any such action, test a repair strategy on a separate disposable
copy of this snapshot, verify SQLite integrity and representative retrieval,
and define a rollback procedure and maintenance window. A full reindex is
not assumed safe until availability of every source document and index
configuration is verified. Until then, production retrieval correctness
cannot be accepted.

Primary semantics: [SQLite virtual-table integrity](https://www.sqlite.org/vtab.html)
and [SQLite FTS5 integrity/rebuild](https://www.sqlite.org/fts5.html).

## Owner-authorized disposable-copy repair trial

After the read-only diagnosis, the owner approved a trial on a **second**
independent copy, `.tmp/production-index-backup-20261022-01-rebuild-trial/`.
All 11 files matched the preserved snapshot by SHA-256 before the trial.
Only the trial copy's `chroma_db/chroma.sqlite3` was targeted by the FTS5
`rebuild` special command. The command was executed in a SQLite transaction
and took 12.55 seconds. The original snapshot was not opened for writes.

| Check | Before trial | After trial |
| --- | ---: | ---: |
| `PRAGMA quick_check` | FTS5 malformed inverted index | `ok` |
| `PRAGMA integrity_check` | FTS5 malformed inverted index | `ok` |
| Embedding rows | 151,062 | 151,062 |
| FTS rows | 151,062 | 151,062 |
| Collections / segments | 1 / 2 | 1 / 2 |
| FTS `MATCH 'hal'` | 19,478 | 19,534 |

For three representative terms (`hal`, `model`, `image`), post-rebuild FTS
row-ID sets contained every prior hit and respectively added 56, 5, and 62
hits. This demonstrates changed search behavior, not independently proven
answer correctness; FTS matching is not equivalent to a literal SQL `LIKE`
comparison for every Unicode/case-folding case.

ChromaDB 1.5.9 opened the trial directory with telemetry disabled. It listed
one collection with 151,062 items, read one stored embedding, returned three
nearest neighbors for that embedding (self-distance 0), and returned three
IDs from a bounded `where_document` filter. No document text, IDs, or
embeddings were printed. A later `PRAGMA integrity_check` still returned
`ok`. All ten non-SQLite trial files remained hash-identical to the first
snapshot. A post-trial SHA-256 comparison found all 11 production files still
identical to the first snapshot.

**Residual finding:** `PRAGMA foreign_key_check` reports the same two
`segments` → `collection` violations in both the original snapshot and the
trial. FTS5 rebuild did not create or resolve them. Chroma's bounded reads
worked despite those violations, but this is not enough to certify all
metadata and write paths. The cause and operational impact need separate
investigation before any production change.

A follow-up read-only schema check on the trial clarified the mismatch:
`segments.collection` declares `REFERENCES collection(id)`, but the database
has `collections`, not `collection`. Both segment rows join successfully to
`collections.id`, and neither collection reference is null. The two reported
violations therefore reflect a stale/invalid declared parent-table name in
this schema, not evidence that these two segment records have lost their
actual collection. This does **not** establish that future writes or migrations
are safe; no schema change was attempted. SQLite documents that a foreign-key
declaration may name a parent table that does not exist and fail at DML time:
[foreign-key semantics](https://www.sqlite.org/foreignkeys.html).

This trial supports a narrowly scoped FTS5 repair strategy; it does not
authorize applying that strategy to production, replacing the index, or
claiming the whole index healthy. A production plan must account for active
writers, a fresh consistent backup, the unchanged foreign-key anomaly,
representative user-facing retrieval checks, downtime, and rollback.
