# PR #865 reconciliation with PR #854

This is a worker handoff for independent review. Final review and terminal CI remain with the release captain.

## Lineage and overlap

- Original integration base `7018e0edebbc370b999005a857230bf3c3a1ad8b`.
- Pre-reconciliation worker head `45939369dcf915660c43a83d3cf54d1348ee4dc3`.
- Fetched integration `7d037b07d4b98b34c6c0ad3026811c7d2f28ae47`.
- Normal reconciliation merge `4561ec2b47a2fe6af86157c67e00c3b8c2d55948`.

PR #854 changed the shared shell contract to derive API keys from the validated release-profile CLI. PR #865 derives web keys from that same CLI. Their profile and Render declaration edits merged cleanly, but their loader failure behavior had semantic overlap.

The initial combined tree produced 4 failures and 68 passes in the configuration suite. Existing tests for missing tool, missing profile, invalid profile and partial output observed a zero return code and `CONTRACT_LOADED` after a failed loader. The API loader's early `return 1` prevented the web fatal guard from running. A plain sourced caller then continued. The integration version contains this return; the earlier worker has only the web fatal guard.

The one-line reconciliation changes the API loader failure to `exit 1`. The shared contract already stops callers on fatal web configuration and required environment failures. Actual script callers source the contract; production tooling uses shell error flags. Both API and web key arrays continue to derive from the validated canonical profile. No second key list or model-facing text was added.

## Verification

The healthy Python environment is `/private/tmp/cuadrao-scipy-env-20261005/bin/python`, version 3.11.15. Tests use `PYTHONPATH=web:src:.`, `--no-cov` and `-p no:cacheprovider`.

- Configuration, exact-key parity and API/web loader tests, 72 passed.
- Recovery and account security tests, 51 passed with 159 assertions.
- Required free mocked eval checks, 272 passed.
- Actual macOS Bash 3.2.57 loader checks, 17 passed. They test a checkout with spaces, an outside working directory, nounset, missing tool, malformed profile, empty success, partial failure and resolved API/web key sets. Run `python docs/reports/evidence/865/verify-reconcile-loader.py` from the checkout root to repeat them.
- Combined-tree modularity budget, passed with no violations. This checkout includes the fetched integration through the recorded normal merge.
- Bash syntax, scoped Ruff and `git diff --check`, passed.

The initial red run used the root checkout's preserved Python 3.10 environment. Its failures were loader assertions, not environment errors. The green run uses the healthy Python 3.11 environment.

The trusted Cloudflare header contract, stable absent-header bucket, malformed trusted address rejection, email/global limits and YAML anchor remain unchanged. Prior recovery evidence is retained, and the affected offline recovery tests were also repeated after reconciliation. Earlier configuration parity evidence is superseded by these combined-tree results.

No real environment file, hosted setting, service, database, physical device, provider, browser or paid eval was used. Full TypeScript checking remains out of scope with the existing 8,030 baseline diagnostics tracked by issue #866. Integration CI and the independent final review remain pending.

Fix Root Causes changed the failed loader boundary instead of suppressing its assertions. Prove It Works drove the actual Bash loader and recovery handlers, then checked the combined tree budget.
