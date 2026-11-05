# Release UI reconciliation verification

Independent review: PASS+NOTES. Captured October 4, 2026 at
`8792abc3941f89a31d2c2dd95f8be93e5d7f5b93` on Xcode 27, iPhone 18 Pro,
iOS 27.0 simulator. This is a fresh bounded pass, not physical-device acceptance.

Debug and Release builds passed. All nine host runners passed through
`ios/scripts/cuadrao-design-mac-pass.sh checks`. The focused native run passed
24 tests, zero skipped and zero failures; [the exported summary](ui-summary.json)
retains the simulator and result. [Command outcomes](summary.txt) retain timings.

The focused selections covered ReleaseUIJourneyTests, Profile follow-ups,
Spanish money entry, shared-group repayment, empty history and the paired voice
predecessor/locked-recording journey. They exercised actual simulator UI. The
previous complete candidate suite remains separately recorded as 119 passed,
48 skipped and zero failures in the [recovery report](../../cuadrao-mobile-recovery-2026-10-04/README.md).

## Revalidation after reconciliation

The iOS tree is `93c02eae19e61b8cf858b2efd2ecc2fcb81f26ea`, identical to
reviewed original #790 head `53a4d67d`. Final integration reconciliation at
`dc3c4dcc087d277223376003c36110190554f780` adds only #809 QA script/tests.
Its iOS tree remains identical, so these app, test and build-config results
remain applicable. Subsequent evidence-only commits do not change this tree.
Full PR patch ID before this evidence commit:
`9270bdbe99f5033e6749ea2e1b98e1d30ef27821`.

## Selected screenshots

- [Profile release availability](profile-release-gates-en.png): DEBUG fixture of release visibility, not a signed-in production session.
- [Settings clearance at large text](profile-signout-large-clearance.png).
- [Money entry before Create](money-valid-plan-es.png).
- [No-data and moved-history presentation](no-data-moved-history-es.png).
- [Actual Release ignores preview arguments](release-preview-arguments-ignored.png): the installed Release app opens the ordinary auth-disabled financial sample, not the preview or gallery.

## Limits and evidence correction

The Release binary excludes the active preview/review entry strings and release
gallery types. It retains two inert `--design-gallery` strings, also present in
prior accepted evidence. [Binary inspection](release-gates.txt) records the
specific checks. The actual Release launch used `--cuadrao-release-ui`,
`--cuadrao-design`, and `--design-gallery`; the screenshot above verifies those
arguments did not open a preview. Do not summarize this as all preview strings
being absent.

Physical touch, real sign-in, connected deletion, remote avatar persistence,
provider setup and external TestFlight acceptance remain open. No provider,
hosted setting, data migration or phone installation was performed.
