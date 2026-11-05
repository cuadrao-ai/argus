# A14 server auth session evidence

Evidence for the fix that stops the API's Supabase Auth client from keeping
user sessions. Finding A14/F1 comes from
[the native auth session proof](https://github.com/lagarcess/argus/pull/726).
Files hold statuses, error codes, counts, and booleans. The regression file
quotes only the fake test tokens its own tests create.

| File | What it shows | Level |
| --- | --- | --- |
| `regression-red-green.json` | `tests/test_auth_client_isolation.py`: all three checks fail on the test-only commit `dd346924e` and pass at `be81feb91`. Failure reasons are the defect itself: a later sign-in sent an earlier user's token, the server refreshed returned sessions, and concurrent sign-ins carried a user token | Unit, real SDK, fake Auth server |
| `real-stack-base-vs-fix.json` | CI's local-Auth and Postgres test files against one local stack, base tree `3b9313f3d` versus fix tree `54fe7b6fe`. Only the new isolation test differs. The same 7 tests fail on both, from this stack's non-default auth config | 3, local Supabase |
| `http-session.json` | #726 session suite against the API at the fix. A14 passes: after the token expired, the untouched session still had 1 refresh token and 0 revoked, and the client's own refresh returned 200 | 3 |
| `http-guest.json`, `http-guest-adapter.json`, `http-callbacks.json` | Guest claims, the synthetic adapter's claims, confirmation and recovery callbacks are unchanged | 3 (adapter: 2) |
| `http-captcha-turnstile-*.json` | CAPTCHA is still forwarded and enforced, in three Cloudflare test-secret modes | 3 |

Every `http-*.json` records two heads. `probe_checkout_head` is the read-only
#726 probe checkout (`de61fd3e7`). `argus_api_head` is the Argus code that
served the requests (`54fe7b6fe`). Later commits change only tests and
evidence, not `src/`. The lane stack is `argus-native-auth-proof`, with `jwt_expiry = 60` and email confirmations on.

Not re-run: the iOS simulator suite. Its I3 check worked around this defect by
signing a decoy in first. The client code is unchanged, and A14 proves the
server-side property for any client. Android remains unverified.

Full backend suite in a Linux python:3.10 container: base `3b9313f3d` 92 failed, 9127 passed, 630 skipped; fix 92 failed, 9130 passed, 631 skipped. The same 92 tests fail on both because of the container, not the code: its source copy has no `.git` metadata (33 provenance and `git rev-parse` failures), it has no Bun (25), and shell scripts it cannot run exit 127 (11); the rest are release-config and import-boundary checks that shell out. The only differences are the new tests.
