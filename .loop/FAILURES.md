# Failure Log

Failures are append-only. A resolved failure remains here with its root cause
and regression test so a later loop cannot reintroduce it.

## Historical constraints carried into Loop 000

| ID | Symptom | Root cause / rule | Regression guard | State |
|---|---|---|---|---|
| FAIL-0001 | Trace changes destabilised streaming chat | Trace must stay out-of-band and non-blocking; it must not own ConversationService, AgentRuntime, or SSE lifecycle. | Trace API and chat-stream regression tests | RESOLVED |
| FAIL-0002 | Feishu appeared to stream a few characters every several seconds | Blocking remote message updates stalled upstream token consumption. | Background/coalesced updater and Feishu bot tests | RESOLVED |
| FAIL-0003 | Agent requests missed MCP tools during slow discovery | MCP discovery was on the critical path or catalog was incomplete. | Domain-aware readiness tests | RESOLVED |
| FAIL-0004 | Baseline MCP registration test expected synchronous agent discovery | The test exercised a pre-lifecycle implementation rather than the catalog registration seam. | Catalog metadata and agent trigger tests | RESOLVED |
| FAIL-0005 | OpenAPI contract rejected implemented Trace/Jev/retrieval endpoints | Exact expected operation-id set was not updated with deliberate public endpoints. | Updated exact operation-id contract | RESOLVED |
| FAIL-0006 | Full regression is red after application-layer chat migration | 18 tests still mock the retired API chat execution seam or use `hi`, which is intentionally a no-LLM greeting. | Explicit Agent-route tests and current application seam mocks | RESOLVED |
| FAIL-0007 | Assistant said it could not inspect local folders or compare duplicate files | Filesystem MCP was configured but not ready in the catalog when routing/classification skipped filesystem intent; the Agent had no native scoped inspect/import tools. Ingestion deduplication only compared against external copies. | Filesystem routing cases, allowlist enforcement, hash-only compare fixtures, tracked cross-source duplicate regression, approval and Capability API tests | RESOLVED |
| FAIL-0008 | A short “why can't you access it?” follow-up repeated the Direct model's generic local-filesystem disclaimer | Intent classification ignored the immediately preceding explicit filesystem task, so the follow-up bypassed Agent tools despite the target being allowlisted. | `test_smart_router_routes_filesystem_access_followup_from_recent_file_task_to_agent` and unrelated-context negative case | RESOLVED |
| FAIL-0009 | A configured Vercel Jev key appeared enabled while every ranking call fell back | The adapter sent `vck_` Gateway credentials to TypeSafe's own host (401) and swallowed the response as a fallback. | Provider-endpoint mapping, explicit synthetic connection check, 401/403 fallback memoization, and Settings API/UI tests | RESOLVED — Gateway now returns 403 at its own endpoint; account authorization remains external |

## Entry format

`FAIL-XXXX`: loop, symptom, root cause, attempted fix, result, correct fix,
regression test, state. Never delete an entry; append a resolution.
