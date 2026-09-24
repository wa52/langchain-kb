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
| FAIL-0006 | Full regression is red after application-layer chat migration | 18 tests still mock the retired API chat execution seam or use `hi`, which is intentionally a no-LLM greeting. | Loop 001: explicit agent-route tests and current application seam mocks | OPEN |

## Entry format

`FAIL-XXXX`: loop, symptom, root cause, attempted fix, result, correct fix,
regression test, state. Never delete an entry; append a resolution.
