# October 17 PR1170 reconciliation

The current candidate preserves PR #1208's canonical legal configuration and shared signup acceptance. PR #1170 keeps the accessible guest contribution Undo, Profile apostrophe cleanup, large-text signup test and guest-notice regressions. Independent exact-head Priya Eval and the full CI outcome remain pending when this receipt is recorded. This is local simulator evidence.

## Integration and ownership

The original writer evidence used integration `6bfa52658c86175e2382e60c9fe9bc9459dbf189`. Preparation started from published PR head `365c2fc21d65445a8898a90cf80d1abc2ccd365b`, whose PR base was `d547945ea51ecb08dc3f7a6d160256da3a3cb770`. Preparation merged `5110e436e2248225ba3c68c63aa3b0280514af3b` normally as `1bd6693a0760f201ac8444648db4d1cc2768dd1f`.

The final one-way integration merge is `398e0ee0f53a85a1246998ddbb1710298f20cc7e`, incorporating `f3899f4aa0d84060e0afaf270f7a983a9f8aa89c`, the squash landing of PR #1208. No published history was rebased. The two text conflicts were `CuadraoCreateAccount.swift` and `CuadraoLegalLinksUITests.swift`. Resolution preserves #1208's canonical signup and legal tests, adds back only the large-text reachability method and removes the obsolete duplicate partial-document test. The canonical legal URL script also matches #1208.

All eight legal/config owner files match integration byte for byte. The built Debug app's legal-links flag remains `false`, recorded in [legal-flag.json](legal-flag.json). No URL, feature flag, hosted service or native private config was enabled or edited by this reconciliation. #1085's scan files were not changed.

## Fresh local checks

Xcode 27.1, build 27A9275, ran eight selected `FinancialLoopUITests` methods on the owned iPhone 16 simulator with iOS 27.0. The process exited 0. The parsed [result summary](ui-summary.json) reports **8 passed, 0 failed, 0 skipped, 0 expected failures**. The [named test output and exact command](focused.log) retain the selection.

The tests cover contribution deletion and Undo restoration, document links opening Safari, partial-document hiding in connected and preview signup, unpublished legal hiding, signup at Large/XXXL/AX5, both-language acceptance and links, guest notice at large text sizes and its absence on the second launch. The UI run exercised the resolved sources before the mechanical merge commit. [Source fingerprints](source-sha256.json) revalidate all 21 affected or canonical files after the merge and after the evidence-only commit.

The contribution Undo and current legal-signup renders were visually inspected. Fresh Spanish images are [Undo](contribution-undo-es.png), [legal signup](signup-legal-es.png), [AX5 signup](signup-ax5-es.png) and [AX5 guest notice](guest-notice-ax5-es.png). Images measure 1178 by 2556 pixels. The earlier SE, Pro Max, connected-profile and contribution-AX5 captures remain historical. Older signup legal wording is superseded by #1208.

The [legal owner check](legal.log) passes Debug and Release. The [merged-tree modularity check](modularity.txt), credential-literal check and diff whitespace check pass. The branch ownership script reports that this existing branch has no ownership policy and skips enforcement.

## Financial model baseline

Before final legal reconciliation, exact integration `5110e436e` and the reconciled branch each ran 202 macOS Swift model methods. Each has 198 passed methods, four failed methods, zero skipped methods and six failed assertions. The [comparison](model-comparison.json) and [actual assertion differences](model-assertions.txt) retain the fresh reproduction:

- `testEmptyPlanSelectionIsAnExplicitJournaledPut`
- `testPlanConfirmationSurvivesRelaunchAndDifferentOwnerCannotReplay`
- `testPostSaveHomeWinsOverEarlierRead`
- `testSearchAccountNavigationAndAcceptedEditsPreserveAccountsSelection`

The financial model inputs, tests and package dependencies did not change between `5110e436e` and `f3899f4aa`; the intervening native changes are the legal/signup/config owner files. This preserves the fresh baseline classification. The model suite is not green. Its four failures were not fixed or silently waived.

## Limits and cleanup

This run uses local guest and signup UI. No backend/web service, model call, paid provider, production action, TestFlight action, migration or PR merge ran. Audible VoiceOver, the OS Reduce Motion toggle and physical-phone behavior were not freshly tested. Dark Mode support remains NOT CHECKED under the assignment. Independent Priya Eval remains a separate gate.

Only the owned simulator `15027D5D-9314-4490-9BB8-0AF5289FA986` and `/private/tmp/pr1170-reconcile-derived` were removed after the test process exited. [Cleanup accounting](cleanup.txt) records 3,891,888 KiB allocated across those two resources before removal and the filesystem readings before and afterward. Concurrent work and filesystem behavior affect global free space. The worktree and ignored `Local.xcconfig` are preserved. Raw result bundles, logs and exported attachments remain under `temp/pr1170-prep` and `temp/pr1170-final`. No shared device or process was stopped.

Prove It Works changed the evidence choice. The current parsed test result, rendered screenshots, actual baseline assertion differences and source fingerprints support this receipt instead of a build-only claim or an old verdict.
