# PR 864 combined native acceptance

Independent QA passed on candidate `0a45e1de92037002eb6f836fcca17011fa82626e`.
The original candidate checkout stayed clean. No product source edits, branch
writes, push, merge, deployment, activation, paid turns, physical phone, or live
Apple/Google authorization occurred.

The complete tracked iOS tree is unchanged since currency reconciliation
`7f920b1c14eac6d3642b195b1ec4d127431b450b`. Root integration housekeeping
`13a1a339c` changes only documentation; its parent-to-commit iOS diff is empty.
[Provenance](provenance.json) records candidate source hashes and those checks.
The release captain owns combined-tree integration and CI decisions.

| Check | Actual result | Evidence |
| --- | --- | --- |
| Full ArgusSession package | 139 executed: 135 passed, 4 opted-local skips, 0 failures; 10.466 seconds | package.log |
| Actual SDK/Auth/API/PG/Keychain local checks | All four skipped cases exercised, plus one new real currency write/readback/relaunch/refusal case: 5 passed, 0 skips/failures; 34.448 seconds | swift-live.log, live-cleanup.log |
| Financial error mapper | 1 passed, 0 skips/failures | mapper.log |
| Actual Household models | 50 passed, 0 skips/failures; 0.298 seconds | household.log |
| Additional currency admission case | 1 passed, 0 skips/failures; validation and unknown-linked restore each dispatch zero requests | currency-admission.log, CombinedCurrencyAdmissionTests.swift |
| Actual ProfileAuthModel Apple recovery UI | 4 passed, 0 skips/failures; English/Spanish recovery, linked-email provenance, foreground revocation, busy notification and manual signout | apple-and-gallery-ui.log, apple-and-gallery-journeys/ |
| Gallery plan currency presentation | 2 passed, 0 skips/failures; English personal currency and Spanish group split/repayment | apple-and-gallery-ui.log, apple-and-gallery-journeys/ |
| Primary preference UI, actual local SDK/API | English 1 passed in 30.731 seconds; Spanish 1 passed in 30.401 seconds; no skips/failures/runtime warnings. Both saved USD, relaunched, and read back committed PG USD | primary-currency-en.log, primary-currency-es-419.log, ui-driver.log, primary-currency-en/, primary-currency-es-419/ |
| Actual-model queued-notification dispatch probe | 1 passed, 0 skips/failures; 15.031 seconds. Before 0, after 1; positive control 1, forbidden dispatch 0; screenshot shows BLOCKED staleOperation at check 2 | notification-probe.log, notification-before.json, notification-after.json, notification-result.json, notification-admission/ |
| Profile identity/currency PG/API checks | 7 passed, 0 skips/failures/warnings; 2.55 seconds | postgres.log |

The Apple/gallery run is one six-test run: 151.359 seconds. Its 17 screenshots,
four primary preference screenshots and one dispatch screenshot give 22 images.
Counts above describe separate runs and are not a single summed suite count.
The gallery cases establish localized presentation only. The primary preference
cases establish persistence through current local Auth/API/PG and production
native session/model code.

## Commands and fixtures

The package command used candidate cwd and these explicit caches:

```sh
CLANG_MODULE_CACHE_PATH=/private/tmp/cuadrao-combined-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cuadrao-combined-swift-cache \
swift test --package-path ios/Packages/ArgusSession \
  --scratch-path /private/tmp/cuadrao-apple-session-swift \
  --cache-path /private/tmp/cuadrao-session-spm-cache \
  --disable-sandbox --disable-automatic-resolution
```

The production model runners were `ios/FinancialModelTests/run.py`, filtered to
`testServerFailuresStayConnectionErrorsWhileValidationKeepsItsMessage`, and
`ios/FinancialModelTests/run_household.py`. Their scratch paths were
`/private/tmp/cuadrao-apple-financial-models` and
`/private/tmp/cuadrao-apple-household-models`, with the same explicit caches.
The initial mapper setup omitted its Clang cache and failed before tests;
setting the owned cache fixed that harness-only failure.

The native command was `xcodebuild test -project
ios/ArgusFoundation.xcodeproj -scheme ArgusFoundation -configuration Debug`,
destination `platform=iOS Simulator,id=AD3171CD-69D5-44E9-93AF-1E38FE5FFCD7`,
derived data `/private/tmp/cuadrao-apple-combined-xcode`, cloned packages
`/private/tmp/cuadrao-apple-session-xcode-packages`,
`-disableAutomaticPackageResolution -parallel-testing-enabled NO`,
`-only-testing:ArgusFoundationUITests/AppleSessionJourneyUITests` and
`-only-testing:ArgusFoundationUITests/CuadraoPlanCurrencyUITests`, result
`/private/tmp/cuadrao-apple-combined-ui.xcresult`,
`CODE_SIGNING_REQUIRED=NO`, bundle `local.argus.apple-combined-proof`.

[run.py](run.py) preserves the actual local SDK recipe. The independent package
copy changes only test-fixture allowed ports from API58400/Auth58401 to
API60341/Auth60331 and adds the two standalone verification files retained here.
Its production sources are copied unchanged from the candidate. The driver
temporarily uses short JWT/confirmation-required settings on the exclusively
leased root-local Auth container, then restores the exact original container,
configuration and initial user set. API60341 starts from candidate source.
Baseline API60340 was untouched.

[ui.py](ui.py) preserves primary preference EN/ES acceptance. It uses a private
600-mode xcconfig and xctestrun, two owned synthetic users, current-source API60341
and a local-only CAPTCHA page60345. The page posts the documented public dummy
token directly and loads no external browser script. Each language uses a
different synthetic user. Its final PG query confirms the UI write after
relaunch. Private fixtures/configuration are deleted and credentials are not
retained in this evidence.

The notification probe applies the already-committed
`notification-admission/interval-probe.patch` only to a temporary `git archive`
of candidate `ios/`. It builds a separate bundle
`local.argus.apple-combined-probe` on the same owned simulator. The first probe
passed, but its counter read happened after execution; that read is not claimed
as a measured before. The final cached rerun reset only the owned fake server,
captured before0 before launching, then after1 after completion. The passing
probe and screenshot prove the attempted denied request never reached the server.
No candidate source was patched.

[postgres.py](postgres.py) runs only
`tests/test_profile_apple_identity_postgres.py` and
`tests/test_profile_currency_api_postgres.py`, with `PYTHONPATH=web:src:.`,
disposable PG60332, local Auth60331 and signed synthetic proof enabled.

## Warnings and limits

The Apple UI run reports `Publishing changes from within view updates is not
allowed, this will cause undefined behavior.` This exact warning also appears
in the earlier independent `cuadrao-apple-review-journeys.log` and admission
journey log. The weak `auth` capture compiler warning also appears in the prior
admission log. AppIntents metadata extraction reports no framework dependency
in both current and earlier runs. The sandboxed package setup additionally
reports inaccessible user-level Swift configuration/security caches and uses
explicit owned caches. These are preserved in logs. No new failure or changed
boundary behavior accompanied them; the scoped primary preference runs report
no runtime warning. No unrelated UI rewrite was made.

Physical Apple credential state, Apple/Google authorization, hosted behavior,
phone acceptance, activation, release readiness and exact-head CI remain the
release captain/founder's separate gates. A synthetic typed Apple checker is
not live Apple provider proof.

## Cleanup and publication

[cleanup.json](cleanup.json) verifies root Auth health200 and PG availability,
own API60341/CAPTCHA60345/fake59920 ports free, own UI users absent, private
configuration removed, candidate clean, and owned simulator deleted. The live
driver additionally verifies exact original Auth container/configuration and
initial user-set restoration. No root DB, foreign process, frozen simulator,
physical phone or Preview installation was stopped or modified.

Text evidence was scanned against actual local credential values without
printing them. One match was removed from copied build output. API request logs,
private fixture files, full Docker inspect JSON, credential-bearing runners and
xcresult containers are not published here. The release captain must commit or
attach this durable evidence folder before a merge-ready claim; this reviewer
does not publish or alter the candidate branch.
