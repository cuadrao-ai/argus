# Apple session and primary currency reconciliation

The original integration base is `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce`.
The previous published PR #864 head is `9419001712dc9f070741909312982f19d1e08e72`.
The fetched integration is `2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`.
The normal reconciliation merge is `b7b9bb555da8f983dcc9e841ca415706f7ce6324`.
No published history was rebased.

## Shared owners

PR #853 adds server currency fields to the existing SessionProfile, a currency
mutation to SessionController and its caller in ProfileAuthModel. PR #864 uses
those same session owners for grant provenance, Apple validation and capture.
The merge keeps both changes. ProfileAuthModel's textual conflict joined two
independent methods at the same location. The test-server conflict now returns
both the server currency fields and optional Apple subject in one /me envelope.
The fixture changes its currency only after a successful PATCH.

The currency mutation retains authenticated phase, identity revision and profile
owner checks. It uses the same authenticatedResponse that checks usable session
access before dispatch, after SDK suspension, before a 401 retry and after its
response. Apple validation can therefore deny currency dispatch through the
existing session owner. The mutation's readback uses the existing loadProfile
validation path. No second provider or currency cache was added.

SessionProfile preserves the new optional currency fields. Missing legacy fields
remain unknown. ProfileAuthModel preserves capture notices and currency changes.
The connected Profile keeps the existing currency selector without UI redesign.
The sparse profile PATCH and update-only gateway from #853 remain intact and
retain the concurrent-edit fix. The Apple identity projection remains owner-only.
No OpenAPI schema changed during reconciliation. The existing artifact compatibility
tests passed, so it was not regenerated.

## Current local proof

- Focused profile, identity and OpenAPI tests passed **112 tests**, with **70
  deselected**, **zero failures** and **zero skips**, in 7.85 seconds.
  The complete test result is in [backend.txt](backend.txt).
- The README-owned ten-file free mocked eval command passed **272 tests**,
  with **zero failures** and **zero skips**, in 9.93 seconds. The result is in
  [mocked-evals.txt](mocked-evals.txt).
- `scripts/check_modularity_budget.py` reports **zero violations** on the combined
  tree. `git diff --check` passed.

The focused command was:

```sh
python -m pytest tests/test_profile_apple_identity.py \
  tests/test_profile_theme_retired.py tests/test_openapi_compatibility.py \
  tests/test_alpha_api_supabase.py tests/test_home_country.py \
  -k 'profile or me or openapi' -q --no-cov
```

Both Python commands used `PYTHONPATH=web:src:.` and
`/private/tmp/cuadrao-scipy-env-20261005/bin/python`. No PostgreSQL, Auth service,
provider, hosted environment, root .env or real user data was accessed.

## Pending combined native proof

This merge changes native session types, mutation callers and the shared fixture.
Earlier package, live Auth/API/Keychain, model and simulator evidence describes
its recorded source only. It does not verify the combined source at this merge.
The Mac slot and simulator are owned by Counsel, so no Swift build, package test
or simulator operation ran during reconciliation.

Before a merge-ready claim, the release captain must obtain independent review,
run the combined session package and affected models, prove currency writes are
blocked during Apple validation and unknown linked-session reauthentication, and
run the affected Apple recovery and primary-currency English/Spanish simulator
journeys. Check real local profile persistence and identity projection as affected
by the combined API, then wait for exact-head CI. The captain owns the database
lease and Mac schedule. Physical Apple state and provider authorization, hosted
acceptance and activation remain separate open gates.

This worker created no services, simulators or background processes. Its test
processes exited. It leaves the branch and committed evidence for independent
review and the captain's single integration merge queue.
