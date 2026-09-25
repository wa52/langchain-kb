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
