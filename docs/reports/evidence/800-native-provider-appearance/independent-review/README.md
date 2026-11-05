# Independent provider appearance review

October 5, 2026. Independent reviewer, not the implementation author. Verdict: PASS+NOTES for the bounded appearance change.

- Reviewed head: `e8a5c10e908f45983cbe1023454ee4a52af765cd`.
- Current integration baseline: `26c0692d634953bd542a6cca6504138e6e420e6c`.
- Original integration base: `a6688eea10895d9f57664f1ece8a7eba96503732`.
- Author tested source/reconciliation merge: `99b903090881e741a093b30fde5d00a9df2d7863`; all subsequent changes through reviewed head are evidence-only.
- Stable patch ID from `git diff BASE HEAD | git patch-id --stable`: `28d4eaad39436b557e42cc76f417a897e1a7a473`.
- Binary-inclusive variant from `git diff --binary BASE HEAD | git patch-id --stable`: `1c3c49160efddbe75019419944b22198bf6db420`.
- Native-only patch ID: `e07fe070811c18cb6b893a7d74f343edd1bbb05a`.

## Independent execution

Two detached review worktrees and separate DerivedData directories were used. The head was clean. The baseline received only the unchanged `NativeProviderAppearanceUITests.swift` from the reviewed head; its production files remained identical to integration. The original and current integration bases have identical `ios` trees.

Both ran the committed `../verify-command.sh` from their respective repository root, with isolated `SIMULATOR_ID` and `RESULT_DIR`. The baseline used the head's script path because the evidence directory does not exist in the baseline. The only configured endpoints were `127.0.0.1:9`, and public provider identifiers were synthetic. No provider button was tapped, no fixture server was started, and no real authentication was attempted.

The independent simulator was iPhone 18 Pro, iOS 27.0, UUID `97B97D04-0B6A-4B81-8B7A-C3EE070226FC`.

| Source | Tests passed | Failed | Skipped | Appearance scenarios | Screenshots |
| --- | ---: | ---: | ---: | ---: | ---: |
| Integration baseline | 3 | 0 | 0 | 16 | 32 |
| Reviewed head | 3 | 0 | 0 | 16 | 32 |

The three tests are both `CuadraoSignInPresentationUITests` tests and `NativeProviderAppearanceUITests/testConnectedProviderAppearance`. The matrix covers sign in/create account, English/Spanish, light/dark and standard/Accessibility XXXL. It verifies structure and full footer frame containment; colors and visible text require image inspection.

Independent configuration compilation/execution passed 11 Debug and 11 Release cases. Merged-tree modularity and whitespace checks passed. The current integration base is already an ancestor of the reviewed head, and the integration advance changes recovery Python tests and documentation without native overlap.

## Visual and code verdict

Representative fresh baseline/head images were visually inspected across both forms, languages, appearances, standard text and Accessibility XXXL footer views. Baseline dark mode has the fixed white canvas and low-contrast secondary footer text. Head correctly selects official Apple white/black and Google SDK dark/light variants and gives the entry form and footer readable system colors. All 64 fresh screenshots are preserved here, including every complete footer capture.

Inspection of the pinned GoogleSignInSwift 9.2.0 source confirms its official dark variant is blue with white text. The patch does not recolor the provider mark. Authentication callbacks, nonce handling, busy disabling, cancellation, provider order and configuration owners are unchanged. No actionable regression was found in the bounded diff.

## Notes and evidence limits

Google's visible Accessibility XXXL label still clips in both baseline and head. [Issue #856](https://github.com/lagarcess/argus/issues/856) remains open, assigned to `lagarcess`; full Dynamic Type acceptance remains incomplete. These passing structural tests do not waive that gate. Busy/cancel behavior is preserved by diff review, not exercised by provider interaction. VoiceOver audio and physical-phone provider authentication were not tested.

At the frozen-head CI check, all applicable checks were successful; two docs-checks and Supabase Preview were skipped. There were zero unresolved review threads. The release captain must recheck CI and source identity after any later publication commit.

The simulator was deleted after the runs, with absence confirmed. Review worktrees and their build outputs are cleaned up; raw xcresults and logs are retained in the separate local evidence directory. This review does not authorize merge, provider activation, hosted changes or deployment.
