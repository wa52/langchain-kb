# Loop 012 — Jev Provider Routing and Connection Visibility

The configured Jev credential is a Vercel AI Gateway key (`vck_` prefix). The
previous adapter sent it to TypeSafe's direct `/v1/systemone` host, which
returned 401. Vercel documents a TypeSafe-compatible endpoint at
`https://ai-gateway.vercel.sh/typesafe/v1/systemone` and model
`typesafe-ai/jev`.

The adapter now selects the endpoint by key provider. The Settings page has an
explicit connection test with a fixed synthetic tool-choice query. It reports
only provider, availability, and HTTP status; neither the key nor provider
response body is returned. A saved key is shown as configured, not proven
active. A 401/403 suppresses repeated Agent-side network attempts for that key
in the process; a new key clears the suppression, and the explicit test always
reprobes. Rule selection remains the fallback.

## Evidence

- Direct-host synthetic probe: HTTP 401.
- Gateway-host synthetic probe and live Settings UI: HTTP 403. The UI displays
  the rejection and says rules are in use. One transient connection-error
  result was also observed; a repeat returned the reproducible 403.
- Focused selector, Settings API, and OpenAPI tests: 43 passed.
- Full regression: 793 passed, 1 skipped, 3 warnings. The first sandboxed
  run exposed a Feishu test's shared repo-root JSON path; that test now uses
  `tmp_path`. A later sandboxed run intermittently hit Windows replace access
  denial in a temporary path. The complete run in the normal authorized
  environment passed without a production Feishu code change.
- Web typecheck and production build passed; live page showed the connection
  button and the 403 state.

## Blocker and remaining work

The Gateway account rejected the real Jev request. The service cannot produce
a real Jev ranking or a Rule-vs-Jev quality comparison from this key until
Gateway authorization is corrected. No quality threshold is claimed from the
11-case offline simulation. The probe used only a synthetic query; no user
chat or knowledge files were sent.

Official reference: https://vercel.com/docs/ai-gateway/sdks-and-apis/typesafe
