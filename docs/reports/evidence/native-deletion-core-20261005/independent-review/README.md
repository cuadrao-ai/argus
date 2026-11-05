# Native deletion core independent QA

Scoped command-core QA passed at
`cc58b16f7f8ee4f520ffa4658f1396ba7a0cc4d7`.
The candidate checkout stayed clean. No source fix, push or branch write was
made by this reviewer. Root owns prerequisite landing, reconciliation, CI and
release decisions. The final app deletion entry, confirmation, Apple adapter,
support interaction and receipt-filesystem adapter are outside this candidate;
this is not a completed UI journey or physical-phone acceptance.

## Actual results

| Check | Result | Evidence |
| --- | --- | --- |
| Full current ArgusSession package | 168 executed: 164 passed, 4 opt-in local-stack skips, 0 failures; 11.484 seconds | cc58-package.log |
| Fourteen deletion cases plus the exact five existing Apple/name regressions | 19 passed, 0 skips/failures; 0.036 seconds | cc58-focused19.log |
| Production Swift SDK/transport with current local API, real Auth/PG/Keychain | 1 passed, 0 skips/failures; 0.750 seconds | cc58-live-sdk.log, LiveDeletionTests.swift |
| Generic iOS Simulator app build, including minimal app-state cases | BUILD SUCCEEDED; no simulator created or app launched | cc58-app-build.log |

These are separate runs, not one summed suite count. The four existing opt-in
package cases were not re-executed here. The preceding #864 evidence owns its
recorded real local session matrix; this run adds a current-source real deletion
command case. No live Apple grant, provider revocation or hosted proof occurred.

The fourteen deletion cases exercise validated 200 and accepted 202, interrupted
response/relaunch, protected-dispatch quarantine, explicit same-command recovery,
no ordinary refresh/capture or one-time-code replay, 503 Retry-After, no-admission
refusals, 401/expired proof with support fallback, malformed done, durable journal
failure, interrupted credential cleanup/receipt recovery, duplicate/stale
snapshots, accepted A/B adoption fencing and notified Apple-refusal fencing.
Several cases contain multiple status/scenario checks.

## Real local boundary

The live case used two new owned synthetic users, current source on API60343,
real local Auth60331, PostgreSQL60332 and the production Swift SDK/transport and
macOS Keychain. It performed:

1. Login A through the current API and obtain its canonical identity.
2. Send one deletion command. The observed result was completed 200, producing
   an exact-A receipt and retiring the local SDK proof without refresh.
3. Login B. While B owned the SDK session, A's completed cleanup receipt was
   suppressed and acknowledgement of that stale receipt was refused.
4. Reconstruct the controller, restore B and sign B out normally.
5. Read PostgreSQL: A was absent, B was present and the new owned deletion run
   was done. Remove the owned fixture users and run, stop API and remove the
   private credential fixture.

[Readback/cleanup output](live-readback-cleanup.log) preserves only nonsecret
process metadata, booleans and run status. The private API request log is not
included. The test's environment explicitly sets APP_ENV=test and leaves analytics
deletion disabled, so the repository's RecordingAnalyticsDeletion adapter
contacts nobody and may count as complete only in this synthetic local setting.
The observed 200 is not evidence of actual PostHog, Apple or other third-party
completion. No Apple identity or authorization code was involved.

The independent package copies production sources unchanged from the exact
tested head. Only the pre-existing live fixture's allowed API/Auth ports change
to 60343/60331, and one new LiveDeletionTests file is added. [Provenance](provenance.json)
records the complete iOS tree and the byte-identical copied package owners;
[port adaptation](fixture-port-adaptation.diff) records the two test-only changes.
The private fixture is 600-mode, generated from the captain's api-env.json and
deleted afterward. No root.env or hosted config is read or copied.

## Regression found and fixed by the source author

Original candidate 40708a935cc78cbaf30b0e9bacb9f1d59110c005 compiled and passed
all 13 new deletion cases, but its full 167 run had eight XCTest failure events
across five existing Apple/name cases, with four opt-in skips. The exact five
cases passed on the actual Name baseline a6efe6e3360f1c4e58c97807b91547de527b0b04,
zero failures/skips in 0.016 seconds. [Failing candidate output](407-package-failures.log)
and [baseline output](a6-baseline5.log) are retained.

The new broad mutating guard in requestCredentialRevalidation rejected
notifications during adoption, capture, an in-flight Apple check and name
initialization. Four cases threw busy. The unreadable-admission case additionally
lost its invalidation fence and returned authenticated instead of validation
required.

The author published cc58. It advances notification generation, avoids deleting
an accepted A journal's proof during active B adoption, preserves deletion
uncertainty and holds Apple access if a notified deletion is later refused.
The original five Apple/name tests stay unchanged. The deletion tests now admit
the notification during B adoption while checking the exact pending proof and
epoch, and add a notified-refusal regression. [Author fix](author-fix.diff)
preserves that scoped change. Full 168, focused 19 and the real local SDK case
passed on the corrected source. No earlier failing run is counted as acceptance.

## Commands

Full and focused package checks used:

```sh
CLANG_MODULE_CACHE_PATH=/private/tmp/cuadrao-combined-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cuadrao-combined-swift-cache \
swift test --package-path ios/Packages/ArgusSession \
  --scratch-path /private/tmp/cuadrao-apple-session-swift \
  --cache-path /private/tmp/cuadrao-session-spm-cache \
  --disable-sandbox --disable-automatic-resolution
```

The focused filter is AccountDeletionTests plus exactly:
testNotificationDuringAdoptionKeepsJournalAndRequiresFreshCheck,
testNotificationDuringCaptureHoldsSessionWithoutReplayingCode,
testNotificationInvalidatesInFlightAppleAnswersBeforeQueuedRestore,
testUnreadableNotificationAdmissionInvalidatesInFlightCheckerAnswer and
testNameCommandIsAwaitedAndLateRevalidationCannotAdoptItsResponse.

The live recipe is [live-driver.py](live-driver.py), with package path
`/private/tmp/cuadrao-deletion-core-live/ios/Packages/ArgusSession`, the same
owned scratch/cache paths and filter LiveDeletionTests. It uses only private
local configuration, dotenv disabled and APP_ENV=test. The account-deletion flag
is enabled only for its owned process. Root Auth configuration is unchanged.
The exclusive run-id before/after set identifies its one synthetic deletion run
for cleanup without touching earlier runs.

The app command was `xcodebuild build -project ios/ArgusFoundation.xcodeproj
-scheme ArgusFoundation -configuration Debug -destination
'generic/platform=iOS Simulator' -derivedDataPath
/private/tmp/cuadrao-deletion-core-xcode -clonedSourcePackagesDirPath
/private/tmp/cuadrao-apple-session-xcode-packages
-disableAutomaticPackageResolution CODE_SIGNING_REQUIRED=NO
ARGUS_LOCAL_BUNDLE_IDENTIFIER=local.argus.deletion-core-independent`.
This compiles current app code; it does not run a UI or filesystem-cleanup adapter.

## Warnings and cleanup

The generic build reports the weak auth-capture warning and skipped AppIntents
metadata extraction already seen in the preceding native reports. Package
checks report inaccessible sandboxed user-level Swift configuration/security
caches and use explicit owned caches. The private API log has the expected local
socket-peer trusted-header fallback and unavailable Apple-revoke configuration
warnings; no Apple link/provider request was part of this synthetic case.

[Cleanup](cleanup.json) confirms own API60343 free, fixture deleted, own test users
absent, root Auth health 200 and PostgreSQL responding, candidate clean, and no
simulator created. The driver verifies cleanup of its owned deletion run. Root
Auth configuration, root DB, foreign services, simulators, Preview and phone
resources were preserved. A short root-approved PG sublease to the session
author occurred between tests; its release preceded this live case.

Text evidence was scanned for actual local credential values and none were
found. Credential fixtures, raw API logs and private configuration are not
published. No provider/paid/hosted work, activation, main modification, merge or
deployment occurred. The captain must commit or attach this folder before a
ready claim, and retain the final adapter/phone/provider gates.
