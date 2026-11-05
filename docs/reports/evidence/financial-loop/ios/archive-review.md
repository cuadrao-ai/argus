# Account archive review follow-up

PR #745 discussion `4131848972` was confirmed against the MVEE’s “Archiving
accounts” requirement: organizational archive hides an account from the ordinary
list, retains its money/history, and provides restoration through Manage accounts.

Source tested and captured: `bbfb3bffc7da1dfbd1309916a6f0847d5d51a32c`.
Product fix: `779cd2776066348a3ddb08ea6555800c0259b431`.
Backend: `92020058d503459dbb7f9e2efa828dd5cddb1637` on the retained local real
Supabase/Postgres stack. This artifact-only commit changes no tested code.

## Actual UI result

`FinancialLoopUITests/testArchiveManagementRestoresSameAccount` passed on September
29, 2026, at 04:41 CDT: **1 test, 0 failures, 58.366 seconds**. This was the only UI
test run; the full financial loop was not repeated.

The test signed into the existing separate verifier identity, created one bounded
synthetic DOP 125 account, and observed:

1. Archive removes its stable account ID from the ordinary active list.
2. Home remains at its captured baseline plus DOP 125 after archive.
3. Manage accounts shows that same account ID in Archived, retaining DOP 125.
4. Opening it and choosing Restore returns that same ID to the active list.
5. Home remains unchanged after restoration.

The known/unknown balance archive→reload→restore model regression also passed in
the 6-test production-model suite. Final simulator compilation, diff whitespace
and native-branch modularity checks passed before this UI run.

## Visual evidence

- [Active list after archive](archive-active-list-dark.png)
- [Manage accounts with the archived record](archive-management-dark.png)

Compared with locked `journey-audit/account-archive.png`: the management view uses
Active/Archived groups, existing quiet rows, and concise archive explanation. The
management screenshot is scrolled to show the Archived group and retained balance;
the management heading and explanation are above the viewport. English/es-419
strings were added; this focused capture is English/dark only.

## Isolation and reproduction

QA used the existing free **iPhone 18 Pro**, iOS 27.0,
`8AFB6084-8918-416E-9164-E21061306BEC`, at 1206×2622 screenshot resolution.
Credentials came from the retained core `verification-client.json`, privately
injected into a mode-0600 temporary xctestrun file and removed after the run. No
credentials or raw auth diagnostics are committed. The founder-demo `client.json`
identity and simulator `197C9C31-77FD-4D31-A9C6-EACA55732B15` were not used or changed.

To repeat, use the existing isolated UI launcher described in
Accounts setup (removed; see tag `archive/ios-personal-2026-10-30`), configure its synthetic test
identity to the separate retained verifier, choose an available simulator, and
select only `ArgusFoundationUITests/FinancialLoopUITests/testArchiveManagementRestoresSameAccount`.
Do not run this mutation test against the founder demo identity. It creates one
synthetic account and leaves it restored; it does not reset or reseed storage.

Local raw result: `/tmp/argus-archive-ui-evidence/ui-1790674787.xcresult`.
Built app: `/tmp/argus-archive-review-derived/Build/Products/Debug-iphonesimulator/ArgusFoundation.app`.
Only the additional QA simulator was shut down at handoff. The founder demo,
API 58400, Supabase 58401, Postgres 58402 and CAPTCHA 58405 remain available. No
hosted changes, deployment, signing or publication occurred in this follow-up.
