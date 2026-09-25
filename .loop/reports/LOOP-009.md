# Loop 009 — Filesystem Follow-up Routing

## Outcome

Fixed the false local-filesystem disclaimer after a user asked why a recent
directory operation could not access its target. The router now inspects only
the immediately preceding user/assistant pair: if the user explicitly requested
a filesystem action and the follow-up reports an access/read/open failure, the
request is routed to the Agent as a read-only filesystem action. Other short
follow-ups keep their existing route. The Agent prompt directs the model to use
`inspect_local_path` and report actual tool errors; indexing still requires an
explicit import request and approval.

## Root cause

`IntentClassifier` classified only the latest message. The contextual follow-up
"怎么又不能访问了" contains no filesystem noun/path/action, so it was routed
to Direct, whose model has no tools and repeated a generic limitation. The
configured path existed and was already inside an enabled filesystem allowlist;
the issue was routing, not filesystem permission.

## Verification

- Regression test failed before the fix on `Route.DIRECT` and passed afterward.
- Focused routing/filesystem/Agent-runtime tests: 39 passed.
- Full project suite: 775 passed, 1 skipped, 3 existing warnings.
- The active API reloaded the changed Python modules; `/api/v1/health` returned
  HTTP 200 after reload.
- Verified the target path's existence and allowlist membership only. No
  directory enumeration, file reads, hashing, or indexing was performed.

## Files

- `src/application/routing/intent.py`
- `src/application/routing/service.py`
- `src/agent/prompt.py`
- `tests/test_smart_router.py`
