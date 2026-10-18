# Native 18+ entry gate evidence

Owner: `age_ios`, GPT-6.1-sol high. Integration base and final reconciliation:
`651870a54be4e5506dbb38f3902fef1a97eef8df`. The remote base was fetched again
before publication and had not advanced. Root owns merges. This PR is held for
three passing receipt-gate runs and independent exact-head Eval before squash.
It must land with the web/API timestamp contract before outside TestFlight.

## Local evidence

- `swift test --package-path ios/Packages/ArgusSession`: 194 tests, four live
  tests skipped, zero failures. Includes no-dispatch refusal without confirmation
  and exact original `age_confirmed_at` in `/api/v1/auth/signup`, with no raw age.
- `run_age_confirmation.py`: 14 policy cases, seven timestamp cases, four range
  boundary cases, seven entry/store/conversion/retry checks, and scoped configured terms URL
  checks. A missing confirmation calls no Apple API. Under-18 refusal survives
  later optional failures in the same gate. Only the timestamp is persisted.
- `run_cuadrao_legal_urls.py`: Debug and Release pass. General legal links stay
  off. The under-18 terms exception uses the validated configured HTTPS URL.
- `run_native_provider_config.py`: 11 cases each in Debug and Release pass.
  Release social providers stay off. Social activation still requires its
  server-side age-confirmation contract before it can ship.
- `run_age_build_settings.py`: simulator, device-default, and Apple opt-in
  entitlement paths pass. Each includes Declared Age Range; Apple opt-in retains
  Sign in with Apple. Deployment remains 17.0. Release social/legal flags remain
  false. These are settings readbacks, not physical-device signing proof.
- Ownership, credential-literal, whitespace, and modularity checks pass.

- Release simulator build passed against SDK 27.1 for arm64 and x86_64 with
  `IPHONEOS_DEPLOYMENT_TARGET=17.0` and signing disabled.

## Simulator UI

Xcode 27.1 (`27A9275`), iOS SDK 27.1, iOS 27.0 Simulator. One owned device:
`Cuadrao Age Gate`, `8CB3EEC1-A07E-4E26-BF41-D91E67EBA91C`.
The inventory had zero booted devices before this one was created. No existing
simulator was stopped or changed.

`AgeConfirmationUITests`: five tests passed, zero failures, zero skips.
The terminal successful result bundle is `/private/tmp/cuadrao-age-ui-pending.xcresult`.
The real shared SwiftUI gate used synthetic Apple responses and no server.
The older-OS case mocks the unsupported platform response; no iOS 17 simulator
runtime is installed, so this is fallback-policy proof rather than an iOS 17 run.

The tests cover a required checkbox, retained exact timestamp after conversion
and relaunch, under-18 refusal without retry, required-sharing decline and error
with Iris's approved Spanish actions, and optional Apple error fallback.
Screenshots are exported from that successful result bundle, with their original
attachment metadata in [the manifest](screenshots/manifest.json):

- [Under-18 refusal and terms](screenshots/82BB65F4-9871-4FBD-BAA6-597B3DBA2E43.png)
- [Required sharing declined](screenshots/400C57B4-57C2-4D86-BC40-024A982044E4.png)
- [Required sharing failed](screenshots/CF711147-548B-407B-807D-7F557B1B7B15.png)
- [Retained confirmation after relaunch](screenshots/531F6A1E-53B4-4893-956E-4E3F26CCF3DE.png)

## Retained failures and limits

Initial compile found an actor-isolated default initializer; the initializer was
corrected. The first test run stopped at the existing Cuadrao build guard because
Local.xcconfig was absent. That guard remains unchanged. Later runs pass synthetic
process-only build values for the guard. No local environment file was written.
The next test selector requested a Button, but the actual checkbox exposes a
Switch. The selector was corrected after a live accessibility snapshot.
The earlier failed bundles and logs remain in `/private/tmp/cuadrao-age-ui*`.
Two owned Xcode processes stalled after failed test methods and were stopped;
the successful run disabled diagnostic collection and returned terminal success.

These checks do not prove a real Apple account response or entitlement provisioning
on a physical device. No phone install, production or hosted writes, provider
calls, migration apply, or TestFlight upload occurred. The API PR owns durable
profile storage; local native tests cannot prove that hosted persistence.

## Release gates and detection

The root coordinator checks three passing receipt-gate runs, independently
reviews the exact final PR head, and checks both PRs together before squash.
CI must finish on the final candidate. The iOS workflow compiles Release for
an iOS 17 deployment target and runs the synthetic UI suite using Xcode 26.6.
[GitHub's official image list](https://github.com/actions/runner-images/blob/main/images/macos/macos-26-Readme.md)
verifies `/Applications/Xcode_26.6.app`, iOS 26.5 SDK, and iPhone 17 Pro runtimes.

Apple runtime guards remain 26.2 for requesting a range and 26.4 for regulatory
features. The build SDK check requires 26.4 or later because an availability
guard cannot supply absent SDK symbols. Sources and the single timestamp API
contract are recorded in [AUTH_SETUP](../../AUTH_SETUP.md#18-entry-confirmation).

Detection signals are a failed age policy/UI/session/entitlement CI check, an
unexpected raw-age persistence field, or a signup missing the exact retained
timestamp. Rollback is a root-owned PR revert together with the API contract;
never bypass refusal or independently enable social providers.
