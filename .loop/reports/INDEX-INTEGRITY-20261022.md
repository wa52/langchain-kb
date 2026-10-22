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
