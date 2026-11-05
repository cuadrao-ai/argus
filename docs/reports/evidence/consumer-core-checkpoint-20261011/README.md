# Consumer core checkpoint, October 11, 2026

This record covers the native signed-in manual-money checkpoint against the existing staging backend. All financial names and amounts in these images are synthetic test data. Nothing here establishes phone, TestFlight or live assistant acceptance.

The later [20:00 UTC continuation](core-continuation-20261011/README.md) initially
reported two passes and two fresh-sign-in failures because the local CAPTCHA
fixture was not running. The [fixture-restored checks](fixture-restored-20261011/README.md)
add passed Account and retained Budget Search journeys, plus manual Budget,
Goal and Search relaunch checks. They preserve the Search timing failures and
the last attempt that stopped at fresh sign-in before checking the final test
repair. The earlier evidence below retains its original source and time.

The later [native authentication preparation](native-auth-preparation-20261011/README.md)
closes at a built configuration-only candidate. It has not been installed or
used for a challenge or login. The lane is stopped for Claude handoff, with
final Search acceptance pending. That record also preserves the local branch
inventory, artifact paths, integration preflight, and cleanup limits.

## Current result

| Check | Result | Source |
| --- | --- | --- |
| Account entry after returning from details | Pass. Three open/cancel cycles. No financial writes. | `ed133f1d9a6725bcc375589daae4096b241f469e` |
| Account entry after the header starts offscreen | Pass. Scroll back, open the picker and cancel. No financial writes. | `ed133f1d9a6725bcc375589daae4096b241f469e` |
| Retained Budget correction sheet and native Back | Pass. Modal blocks Back; Cancel, canceled swipe and completed swipe preserve the corrected activity and Budget total. No financial writes. | `7172fd6ff293cd00e956f255669e0d0b56711f8e` plus retained probe source |
| Budget spending, correction, refund, Search and relaunch | Pass in one complete final execution. Includes correction, cross-account refund, contributor-position restoration, limit edit, removal/restore, Search origin and Spanish relaunch. Earlier failed attempts remain preserved. | `40ff4967040c854ca5dd0764115227544011a6e2` |
| Goal allocation, contribution correction, Search and relaunch | Pass in one complete execution. Includes cancel, allocation, contribution correction, release/relink, target edit, archive/restore, Search origin, relaunch and Spanish display. | `7172fd6ff293cd00e956f255669e0d0b56711f8e` plus retained probe |
| Extreme Dynamic Type, English | Failed and deferred by founder direction. | `b4165692960ba68f69f3a361c1b18b4d4e8837d1` plus preserved diagnostic source |
| Extreme Dynamic Type, Spanish | Not run. Deferred with English. | None |

The three passed regressions and complete Budget and Goal tests each report one pass, zero failures and zero skips. Their summaries are in `results/`. The two earlier Budget attempts each report zero passes, one failure and zero skips; those original results remain preserved. A reached step is not a complete journey pass.

## Source and environment

- Original integration base is `479cc10918db57b454fff27c9c6b9b453bdfa4a6`.
- Latest reconciled integration is `286c6bc0494be6c858851f0c4037ea6df5bacea5`.
- The latest one-way reconciliation commit is `40ff4967040c854ca5dd0764115227544011a6e2`. Earlier reconciliations were `7172fd6ff293cd00e956f255669e0d0b56711f8e` to integration `3c3be1a75af5f5fd1e19db039f76c5684753241c` and `b9ae331d26d20d8947edbc747f9eeb45a62c4fb4` to `1612602c4d94b104378b5a787d3e19abfc07052c`.
- The latest integration change adds Business-only human note contracts, tests, documentation and a migration file. It does not overlap native runtime, Consumer financial or conversation contracts, auth, UI state, environment or affected tests. The migration was not applied. Prior evidence retains its original source identity.
- The first packaged source was `ed133f1d9a6725bcc375589daae4096b241f469e`. `candidate-source.json` records its relevant file hashes.
- Latest tested core source is `40ff4967040c854ca5dd0764115227544011a6e2`. The product iOS tree matches the reconciled integration. Only the test scroll, native Back readiness and complete Budget-state assertion helpers differ.
- The tested `7172fd6ff` package includes the temporary no-write probe retained under `probes/`; `probes/source-retained-budget-native-back.json` records its source and file hashes. The temporary probe is absent from the shipping test target. The new `40ff49670` package has no temporary probe; its successful build and relevant hashes are recorded in `budget-state-candidate-source.json`.
- The staging API is `https://cuadrao-api-staging.onrender.com`. The retained read-only provider check records backend `cad1cbe1ec27ff89c08eadbec31718a0e627383c` in `backend-pin.json`.
- The simulator is `C85CDCF9-E5DB-4A86-97FB-65C46B349B35`, iPhone 18 Pro, iOS 27.0. The bundle is `local.argus.consumer.staging`.
- The local CAPTCHA page supports synthetic login. Financial requests use staging. Credentials and raw authentication logs are excluded from this evidence.

The `ed133f1d9` normal-size results retain their source identity. The Date layout branch was inactive at that size, but these results are not relabeled as a run of a later source. The current package built successfully. An earlier sandboxed build could not access Xcode caches and produced no usable candidate.

## Account-entry failure and repair

The original no-write reproduction failed before opening the account picker. The test reported that `accounts.add` could not reach the visible scroll area.

Two controlled XCTest probes isolated the gesture origin. The old 63-point slow drag began in the chart at y390. The Add button stayed at y775. The identical distance, speed and hold from y585 moved Add to y727.67. An ordinary tap then opened the account picker, and Cancel returned to Home.

The helper now begins an upward drag at 75% of the available viewport and a downward drag at 25%. Its bounded distance, speed, settling, visibility checks and ordinary button tap are unchanged. No product gesture, account action or financial service changed.

The probe source and source hashes are in `probes/`. The frame traces and summaries are in `results/`. Screenshots preserve the before, failed center drag, successful lower drag and picker states. The temporary probes are not part of the shipping UI test target.

## Budget correction failure and repair

The first Budget run saved the correction from DOP 80.00 to DOP 60.00, then tried native Back gestures while the correction sheet was still closing. A read-only canonical staging check confirmed the corrected activity at revision 2 and Budget spending of DOP 180.00. The failure did not establish wrong saved balances.

The old test treated disappearance of `loop.confirm` as completion. That identifier changes when saving starts, before the request finishes or the sheet closes. The tap-based Back helper already waited for the underlying Back button to become hittable; the swipe helper bypassed that precondition. Both now use the same existing readiness check. Gesture coordinates and timing, save behavior and financial services are unchanged.

The retained no-write probe passed on the repaired package. It opens the existing corrected activity, verifies that the modal blocks native Back, cancels, checks a canceled swipe and returns to the Budget with DOP 180.00 spent and DOP 30.00 over limit. The full second attempt then passed the actual saved correction, cross-account refund and contributor-position relaunch before the separate limit assertion failed.

## Budget limit refresh failure

The second attempt changes the limit from DOP 150.00 to DOP 160.00 while spending stays DOP 155.00. Both old and new status labels contain DOP 5.00; only "over budget" changes to "remaining." The test waits for unchanged spending and an already-existing status element, then checks that direction immediately.

The retained final video frame still shows the disabled Save sheet. A fresh canonical read confirms `Food E6886` at version 2, limit DOP 160.00, spending DOP 155.00 and positive remaining DOP 5.00. Its three contributors are the corrected DOP 60.00 purchase, original DOP 120.00 purchase and DOP 25.00 refund. See `results/budget-limit-after-failure-api-readback.json`.

The bounded repair at `1c43f36cc56a8796c1f25442d88104b87cff4c59` waits for the complete expected spending, magnitude and direction together under the existing timeout. No product or financial service changed. Its native build, Swift parse, diff and modularity checks passed. The complete Budget rerun then passed at `40ff4967040c854ca5dd0764115227544011a6e2`.

## Complete Budget journey

The final run passed once with zero failures or skips. The synthetic `Food DF84D` Budget starts with a DOP 150.00 limit scoped to checking and card accounts. A DOP 120.00 purchase and DOP 80.00 card purchase bring spending to DOP 200.00. Correcting the card purchase to DOP 60.00 lowers spending to DOP 180.00. A DOP 25.00 refund into an account outside the Budget scope lowers net spending to DOP 155.00 while preserving that account's unknown balance.

The test verifies the three contributors, contributor position after relaunch, and a limit edit to DOP 160.00 with DOP 5.00 remaining. It then removes and restores the Budget, cancels an edit, opens the Budget from Search, relaunches, preserves the Search origin, and displays the same saved state in Spanish. The final Spanish screenshot was visually inspected; the retained screen shows the expected totals and resolved Spanish labels without visible clipping.

`results/budget-full-pass.json` records the terminal XCTest result. `results/budget-full-pass-source.json` records the exact source, synthetic name, original attachment names and SHA-256 hashes of nine unchanged screenshots. The two existing nested-scroll runtime warnings remain recorded in the result. This test does not establish response-loss recovery or phone acceptance.

The independent code review returned no actionable findings at this source before the final Budget run completed. Its original timing and scope are retained in `review.md`; the terminal test result above closes the pending runtime check without changing reviewed source.

The later [publication review](publication-review.md) confirms the complete result, source attribution and preserved evidence. Publication adds docs and evidence only. That review records the calculated merge with integration `e465c2fe4bf7e2749215bc677a1fa225adab384c`. The actual local merge subsequently completed as `4a953d7e9c07b7b7d057506bb0b630287b6585b9`, with unchanged native source and preserved evidence. Final integration reconciliation, publication, and CI remain pending. Existing runs keep their original source identities.

The [Spanish manual continuation](spanish-refresh-20261011/README.md) preserves
Budget relaunch, Search return and filter checks, cancellation, and Free entry
points on the unchanged Core binary. It includes both the loading and settled
Search captures. It adds no new XCTest or paid-chat result.

## Complete Goal journey

The original Goal journey passed at `7172fd6ff` in one execution with zero failures or skips. It records two synthetic accounts, assigns DOP 600.00 already held, adds a DOP 200.00 contribution, corrects that contribution to DOP 150.00, releases and relinks the existing contribution, and keeps supported savings at DOP 750.00. It then changes the target to DOP 2,500.00, archives and restores, finds the Goal through Search, preserves that origin after relaunch, and renders the saved Goal in Spanish.

The final Budget-only assertion repair, motion documentation and Business reconciliation do not affect that Goal path or product source. Its evidence is retained with the original tested source rather than relabeled as a new run.

## Deferred large-text work

The English stress test opened the account form, used the keyboard and cancelled successfully. Its later transaction Date assertion failed because the full picker extended below the primary action after the test revealed only the Date label. That result does not by itself prove a product scrolling defect. Spanish never started.

The accessibility layout proposal remains on `codex/consumer-core-native-repairs` at `55e06e92985fa6f1593fa89938853ddf78750611`. Current core source removes that proposal. Its screenshots and failed summary are preserved here. Extreme Dynamic Type remains a final pre-TestFlight acceptance task and does not block this normal-size checkpoint.

## Boundaries

No phone, VoiceOver, Switch Control, TestFlight upload, deployment, hosted configuration change, guest unlock, household unlock or provider/model call occurred in this checkpoint. The retained Budget and Goal data must not be deleted to make later tests pass.

The separate one-screen Goal design experiment uses an isolated branch. It does not change the source or acceptance outcome recorded here. Approved chat presentation is preserved; live assistant wiring remains separate from these manual-money results.
