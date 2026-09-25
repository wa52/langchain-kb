# Loop 011 — Abstain on Undocumented HALCON Example Parameters

The objective was to catch the observed failure where parameter semantics,
output types, or operator scope were inferred from a code example.

## Harness and Environment

- Harness: existing `ProductionFastRagAgent` with one example-only fixture;
  invokes production `FastRagService` through its existing retrieval seam.
- Environment: Harbor Docker image contains one synthetic HDevelop example;
  no manual, personal corpus, chat history, MCP, or user file.
- Verifier: independent configured model judge.
- Docker task declares `network_mode = "no-network"`. Harness and judge calls
  are host-side subprocesses, outside that container network boundary. Only the
  public example form and synthetic answers are sent to the configured model.

## Calibration

| Fixture | Expected | Actual |
|---|---:|---:|
| Valid answer reports only call/literals and marks undocumented details unknown | Pass | Pass |
| Plausible answer invents mask size, thresholds, light direction, output, and scope | Fail | Fail |

The judge treats the candidate answer as untrusted data.

## Harbor Result

- Trial `halcon-lines-facet-abstention__8jcuUA2`: 1/1 completed, zero errors,
  reward 1.0.
- One model answer call; Fast RAG total and LLM time were both about 12.03 s.
- The answer quoted the visible call, did not infer the numeric arguments,
  `'light'` semantics, output type, or extracted structure, and cited the
  example.
- Full tests: 786 passed, 1 skipped, 3 warnings.

The first CLI attempt stopped during GBK progress rendering before a trial
started. The pending job was confirmed to have no active task container and
resumed under UTF-8; the final job has no pending or errored trial.

## Limitations

This is a focused regression, not a representative benchmark. Together with
the existing manual-plus-example case, only two HALCON observations exist.
Citation correctness and unsupported-claim thresholds remain UNBASELINED; a
multi-domain benchmark and Evaluation-page presentation remain future work.
