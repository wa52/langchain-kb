# Loop 007 — HALCON Evidence-Boundary Harbor Evaluation

## Prior loop result

Loop 006 delivered an offline Rule-vs-Jev-adapter Tool Selection evaluation and
Evaluation Web page. The current scope is one semantic Fast RAG task over a
frozen HALCON example/reference fixture; it must not load personal corpus,
history, or MCP configuration. See `reports/LOOP-007.md`.

## Goal

Evaluate one production Fast RAG answer against a synthetic HALCON example and
frozen operator-reference evidence, including the evidence boundary between
example code and documented operator behavior.

## Acceptance

- [x] Build a Harbor task containing only synthetic HDevelop and frozen
      paraphrased HALCON 24.11.3.0 operator-reference evidence.
- [x] Invoke the production `FastRagService` with a deterministic retrieval
      fixture instead of initializing the user's corpus or vector store.
- [x] Independently grade the answer semantically and calibrate the verifier
      on one correct paraphrase and one plausible wrong response.
- [x] Retain the Harbor job, answer, verifier verdict, timing, and source digest.
- [x] Run the full test suite in the project `kb_env` environment.

## Scope guard

Do not read live MCP configuration, user prompts, chat history, or the personal
knowledge corpus. Send only synthetic task fixtures to the configured API.

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
