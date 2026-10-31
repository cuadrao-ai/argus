# CI fixture and response-contract repair

CI candidate `257b1c080658c1b578df6c0edfed2cfa873ee578` introduced these test gaps.
The two reported backend cases pass on unchanged integration
`13a1a339cbab1a3896e10779477658af63e062b3` in an isolated archive, **2 passed**
in 1.98 seconds. They both fail on the candidate, **2 failed** in 2.39 seconds.
The first archive test attempt raced archive creation and collected zero tests;
that setup attempt is not a passing baseline. The completed archive run is recorded.

The broad schema assertion still required the shared auth-only 503 reference for
/me even though this PR adds the documented identity-verification failure.
Its bounded /me case now requires both auth_session_verification_unavailable and
apple_identity_unavailable plus the canonical Error schema. All other endpoint
checks remain intact. Production schema, runtime and error behavior are unchanged.

The registered-account truth test supplied a scripted Auth/profile gateway but
no authoritative Apple identity source. Its fixture now explicitly returns
confirmed absence through the canonical identity reader and asserts that the
reader uses the authenticated user ID. It still proves editable anonymous metadata
cannot change the registered account kind or capabilities.

CI's latest real-PostgreSQL matrix collected 731, passed 730 and skipped one.
The skipped case was test_real_local_auth_session_only_exposes_its_owner, because
its extra [removed obsolete setting] opt-in was absent despite the canonical
ARGUS_LOCAL_SUPABASE_* configuration. The case is new to this PR and its file does
not exist on integration 13a1. Its old candidate implementation reproduced **one
skip** with the configured local stack and no extra opt-in, including the exact
reason. The fixed fixture uses the existing local_supabase_gateway and canonical
local configuration. Its explicit loopback assertion remains before any HTTP
call. Missing local configuration may still skip an ordinary unconfigured run;
the required configured CI matrix executes the case. The required no-skip gate
and its workflow are unchanged.

Final focused artifact, guest-policy, identity, name and OpenAPI checks passed
**85 tests**, zero failures/skips, in 8.63 seconds. Full exact lint scope
`python -m ruff check src tests workflows scripts` passed. Modularity reported zero
violations, and whitespace passed. The corrected signed Auth fixture passed **one
real local test**, zero failures/skips, in 1.74 seconds under the root-approved
exclusive PG60332 sublease. Its own synthetic users, identities and allowlist rows
were cleaned in the existing finally teardown, then the lease was returned to QA.
No Auth/container/configuration reset or foreign cleanup occurred.

Trailing spaces in copied pytest failure output were removed before final
publication. Test messages and outcomes are unchanged.

Only test fixtures/assertions and this evidence changed. No production, native,
SQL, provider policy or response source changed. All 51 published QA bundle hashes
and 22 screenshots remain unchanged. The already completed combined native proof
is retained. Independent fix-delta review and terminal new-head CI remain required.
No Mac, simulator, provider, root .env, hosted or paid action ran.
