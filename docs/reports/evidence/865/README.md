# Web release-profile parity follow-up

PR #865, configuration-only follow-up to candidate
`6b4203da31ee10edba99084bbfe018328ef2e00a`.

## Failure and fix

The candidate added the trusted client IP header to the web Render declaration
but omitted it from the release profile and the separate shell key list.
Both existing exact-key parity tests failed with the extra
`ARGUS_TRUSTED_CLIENT_IP_HEADER` key. The eight new loader regressions also failed
before the fix and were committed as `9fe492ea0`.

The web release profile now declares the header. The shell web array reads the
existing validated `allowed-keys web` CLI, which owns fixed, required and optional
keys. Missing tool/profile, invalid profile, empty output, or partial output
followed by a nonzero exit stops the caller before the list can be used. API and
workflow shell arrays are unchanged. Two source-text assertions now inspect the
resolved shell arrays, preserving their key requirements.

Model the Domain kept the profile's existing three key categories as the data
shape. Fix Root Causes removed the duplicate web list instead of adding another
literal to it.

## Verification

All tests are local and offline. No real environment file, provider, email,
browser, physical device, database or hosted service was used or changed.

- Configuration, exact-key parity and shell failure checks, 70 passed.
- Recovery and account security checks, 51 passed.
- Required mocked harness, 272 passed.
- Bash syntax, Ruff and `git diff --check`, passed.
- Combined-tree modularity budget, passed. Original and freshly fetched current
  integration are both `7018e0edebbc370b999005a857230bf3c3a1ad8b`; the working
  candidate already contains that integration tree, so no reconciliation merge
  or intervening semantic overlap exists.

Commands from the checkout root, with the healthy Python environment and
`PYTHONPATH=web:src:.`:

```sh
python -m pytest tests/test_web_env_profile.py tests/test_environment_scripts.py tests/test_private_alpha_release_profile.py -q --no-cov -p no:cacheprovider
bun test web/__tests__/auth-security.test.ts web/__tests__/recovery-client-ip.test.ts
python -m pytest tests/evals/test_measurement_eval_harness.py tests/evals/test_measurement_eval_dca_semantics.py tests/evals/test_measurement_eval_scorecard.py tests/evals/test_measurement_eval_live_environment.py tests/evals/test_chat_runtime_eval_manifest.py tests/evals/test_chat_runtime_trajectory_harness.py tests/evals/test_measurement_availability.py tests/evals/test_measurement_delivery.py tests/evals/test_measurement_outcome.py tests/evals/test_prose_evidence.py -q --no-cov -p no:cacheprovider
python scripts/check_modularity_budget.py
python -m ruff check --no-cache tests/test_web_env_profile.py tests/test_environment_scripts.py
bash -n .github/argus-env.sh
git diff --check
```

The first mocked run had 18 filesystem-permission failures creating `.gemini`
in the assigned checkout outside the sandbox's writable roots. The identical
command with authorized checkout write access passed all 272. The baseline
parity log also includes cache-write warnings. These setup failures were not
code failures and no assertions were weakened.

## Independent review and handoff

A separate read-only reviewer examined the delta against `6b4203da3` and found
no actionable findings. It confirmed actual macOS Bash 3.2.57 sourcing from
outside the checkout, including a checkout path with spaces. Its eight new
regressions passed; after the assertion updates its ten targeted tests passed.
The complete 70-test configuration run above was performed by the writer after
those edits. No-comments review found zero scoped comments, suppressions,
deletion candidates or MUST KILL findings. The reviewer is stopped.

The existing 8,030 TypeScript baseline diagnostics remain tracked in
[issue #866](https://github.com/lagarcess/argus/issues/866). This configuration
slice neither reruns nor claims a green whole-project TypeScript check. Prior
recovery evidence is retained because the runtime delta is unchanged.

The release captain owns the fresh final delta review, exact-head CI, integration
reconciliation with the separately authored API-list change in PR #854, and
any guarded merge. This report is a worker handoff, not a release-ready claim.
