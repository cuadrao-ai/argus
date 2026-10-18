# Independent Eval fixes

Owner `age_ios_review_fixes`, OpenAI GPT-6.1-sol medium. This follow-up fixes the
two independent findings against `7be8ad0cf82c126330f5201dbaa61e38210bbe3e` on
PR #1232. The fetched integration base remains
`651870a54be4e5506dbb38f3902fef1a97eef8df`. Its trial merge matches the reviewed
head tree. No integration delta invalidates retained evidence.

The workflow uses `synthetic-anon-key`. The credential scanner passes without
changes. The Debug legal fixture mounts the real welcome/signup/guest views with
an offline signed-out auth model. Every launch resets the canonical age key on
the isolated test simulator. Each connected legal journey completes the real
checkbox and a fake required adult check, then asserts the existing signup or
guest controls before checking links. Preview one-document checks retain their
preview route and now require the signup title. No auth request is dispatched.

## Verification

The final batch passed all 12 tests with zero failures and zero skips. It used
Xcode 27.1 build 27A9275, iOS SDK 27.1, and the handed-off iPhone 18 Pro simulator
on iOS 27.0, ID `8CB3EEC1-A07E-4E26-BF41-D91E67EBA91C`. The invocation used only
process-level synthetic configuration, including `synthetic-anon-key`.

- Five age cases cover retained timestamp, under-18 refusal, required decline,
  required failure and optional failure.
- Seven legal cases cover guest links absent/present, signup links absent/present,
  both actual document destinations, one-document hiding in connected/preview
  views, and three text sizes. The cases include light/dark and Spanish/English.
- [Test summary](test-summary.json) records the terminal 12/12 result.
- [Screenshot manifest](screenshots/manifest.json) maps 14 retained captures to
  their test cases. Three captures were visually checked for the approved
  under-18 state, real Spanish signup with links and dark guest profile without
  links.
- Credential scanner, branch ownership, modularity, whitespace and workflow YAML
  checks pass. All seven legal selectors and five age methods resolve.
- Age policy checks pass 14 policy, seven timestamp, four bounds and seven
  entry/conversion cases. Legal URL checks pass Debug/Release. Provider checks
  pass 11 cases in each build configuration. All three effective entitlement
  settings checks pass with deployment 17.0 and Release legal/social flags false.

The terminal bundle remains at
`/private/tmp/age-review-fixes-results/test-20261018T051843Z.xcresult`.
Earlier interrupted and failed runs remain in the same results directory. The
first run was interrupted after detecting missing offline restore startup. The
second passed five age tests but failed guest entry because its separate test
store disagreed with the canonical guest guard. The final fixture uses the same
canonical store as guest entry. No production store logic changed.

## CI toolchain and release holds

The earlier native run `39099474877` failed compiling existing swipe/reorder UI
against SDK 26.5. The workflow now uses `xcode-27`, pinned to
`/Applications/Xcode_27.1.app`, with the listed iPhone 17 runtime. GitHub's
[official image list](https://github.com/actions/runner-images/blob/main/images/macos/xcode-27-arm64-Readme.md)
and [October 15 GA announcement](https://github.blog/changelog/2026-10-15-xcode-27-runner-image-generally-available/)
confirm this supported runner. Deployment remains iOS 17. The age API guards
remain iOS 26.2 and 26.4. No unrelated UI changes were made.

Fresh exact-head CI and independent delta Eval remain required. Root still owns
the three-passing-run receipt hold and all merges. Actual Apple responses,
physical-device provisioning and hosted account persistence remain unverified.
No environment/configuration file, provisioning, hosted service, real auth,
email, paid provider, TestFlight or production change occurred.
