# Consumer staging preflight: October 9, 2026

After Lucas approved PR #937, read-only checks against
`https://cuadrao-api-staging.onrender.com` found the manual-money surface disabled.
[Request results](preflight.json) contain no credentials or personal data.

- Health: HTTP 200, healthy.
- Accounts, Home, Plan and financial Search: HTTP 404,
  `financial_accounts_unavailable`.
- Render readback: live deploy `dep-db4ofq142hec73edibig`, backend
  `cad1cbe1ec27ff89c08eadbec31718a0e627383c`, automatic deployment off.
- `ARGUS_FINANCIAL_ACCOUNTS_ENABLED` is absent from the service environment.
  The deployed source defaults it off and checks it before authentication.
  Accounts, transactions, budgets, goals and financial Search share this gate.

These are unauthenticated feature-gate checks, not signed-in journey acceptance.
No hosted setting, schema, account, data, deployment or service was changed.
The native account, money, plan and Search transport files are unchanged between
the deployed backend's source commit and the merged native checkpoint. This
supports proceeding with compatibility tests; it does not prove them passed.

## Approved setup completed

Lucas approved the bounded staging setup after reading this preflight: enable
the financial-accounts gate on `cad1cbe1e`, restart and obtain a synthetic test
login. The existing staging owner completed that work. The request results
above record the pre-activation state. [Setup verification](setup-verification.json)
records the later activation: healthy HTTP 200 and authenticated accounts HTTP
200 on deploy `dep-db4qeilckfvc73fss4kg`, still at `cad1cbe1e`.

Only `ARGUS_FINANCIAL_ACCOUNTS_ENABLED=true` changed. The restart did not apply
the saved environment, so the owner deployed the same pinned commit. Other
environment values, the applied C0/C1 schema and checkpoint ledger are unchanged;
automatic deployment remains off. Current integration needs later Business
columns and must not be deployed under this approval. No newer code, migrations,
guest mode or production change is authorized.

The owner reused the existing registered synthetic staging user and allowlist
entry, changed only that user's test password, and handed credentials over in a
private mode-0600 file. No real user changed and no email was sent. Credentials
are excluded from this PR.

Use the dedicated Consumer simulator with sign-in enabled and preview mode off.
Check accounts, transactions, budgets, goals, search/find later,
per-currency totals, correction history and relaunch balances in English and
Spanish with large text. Retain the accepted #937 evidence. No guest, receipt,
shared-plan, redesign, RevenueCat, accessibility-tooling or phone-install work.

## Native acceptance started, not complete

The Release app and tests were built at `03266e096967acb0201bca914103f6a105d20865`.
Its app and test source are identical to merged checkpoint
`43fac94de2672600079f312258908f05747a9d63`; the intervening commits contain only
landing documentation. The iPhone 18 Pro simulator ran iOS 27.0. Native preview
mode was off and the API origin was `https://cuadrao-api-staging.onrender.com`.

`testAccountEntryKeepsUnknownAndSignedBalances` passed: 1 passed, 0 failed,
0 skipped. It signed in, created an account with an unknown balance, recorded
spending without inventing a balance, corrected its known starting balance to
DOP -25.50 and verified persistence after relaunch.
[Test summary](account-summary.json) and
[relaunch screenshot](account-after-relaunch.png) preserve this limited proof.

Two older transaction tests stopped at Home summary labels that the current Home
no longer renders. The currency reconciliation and release-surface tests both
stopped while opening a second account. These are failed acceptance attempts;
their cause remains under investigation. They do not establish transaction,
budget, goal, search, Spanish or large-text acceptance against staging.
[Money summary](money-summary.json) and [release-surface summary](release-summary.json)
retain all four failures. A subsequent simulator probe found that a 180 ms press
opened the account form while the automation tool's short tap left Home
unchanged. Temporarily disabling the keyboard tap-away recognizer did not change
the short-tap result; it was restored afterward. This narrows the input issue
but does not establish its cause or turn either failed test into a pass.

There is no hosted staging web/CAPTCHA bridge. Native sign-in used the repository's
existing local CAPTCHA test page with its public test keys; credentials went to
staging Supabase and financial requests went to the pinned staging API. This
does not verify a hosted CAPTCHA page or a production sign-in configuration.
There is no new phone acceptance, phone install or TestFlight upload.
