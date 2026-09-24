# Loop 001 — Chat Execution Regression Contract Alignment

## Prior loop result

Loop 000 established the contracts and baseline in
`reports/BASELINE-000.md`. It completed its inventory purpose and selected
this red regression gate as the next highest-priority gap.

## Acceptance

- [ ] Agent-chat tests use an explicit Agent route, not a greeting/generic
      Direct route.
- [ ] CLI tests mock the current application seam rather than the removed API
      execution seam.
- [ ] Existing greeting/direct behaviour remains covered and unchanged.
- [ ] Full isolated Python suite passes with the project-local temp directory.
- [ ] No production ConversationService, AgentRuntime, or SSE lifecycle code
      changes are required solely to satisfy obsolete mocks.

## Scope guard

Do not modify production chat execution, SSE lifecycle, RAG scoring, agent
selection, or Feishu delivery. This loop is regression-contract alignment.
