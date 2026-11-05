# Native Apple name independent QA

Scoped QA passed at published source
`a6efe6e3360f1c4e58c97807b91547de527b0b04`.
The candidate checkout stayed clean. This report is local verification, not
permission to merge, activate providers, deploy, or claim physical Apple proof.
The release captain still owns #864 landing/reconciliation and exact-head CI.

## Actual results

| Check | Result | Evidence |
| --- | --- | --- |
| Full current ArgusSession package | 154 executed: 150 passed, 4 opt-in local-stack skips, 0 failures; 11.475 seconds | a6-package.log |
| Fifteen new name cases plus existing sign-out recovery regression | 16 passed, 0 skips/failures; 1.051 seconds | a6-focused16.log |
| Three independent changed-boundary cases | 3 passed, 0 skips/failures; 0.023 seconds | a6-independent3.log, IndependentAppleNameBoundaryTests.swift |
| Signed current source local Auth/API/PostgreSQL name journey | 1 passed, 0 skips/failures/warnings; 2.67 seconds | a6-signed-local.log, signed-local.py |
| Actual native provider configuration | 11 Debug and 11 Release cases passed. Release providers remain off | a6-provider-config.log |
| Actual ProfileAuthModel first-name UI journey | 1 passed, 0 skips/failures; 13.480 seconds. Four screenshots, no runtime warnings | a6-ui.log, a6-ui-summary.json, journey/ |

These are separate runs, not one summed suite count. The four opt-in package
cases were not re-executed here; the preceding #864 combined-native report owns
its recorded real local SDK/Auth/API/PG proof. This slice adds current name
regressions, actual-model local transport/Keychain proof and one signed current
server-command journey. No live Apple grant was performed.

The fifteen new cases executed, covering durable callback intent before grant,
Unicode/trim, canonical awaited name response, transient name outage, lost grant
and name responses, relaunch without authorization-code replay, later explicit
name/clear no-ops, mismatched subjects, stale identity/signout, denied adoption,
SDK storage rotation, unknown grant refusal, expiry, late revalidation, uncertain
Apple validation, callback write failure, durable acknowledgement failure and
recoverable adoption failure. Several cases contain multiple scenarios.

The independent cases prove capture503 still permits name initialization without
code replay, stale account-A retry sends no request and does not seed account B,
and a subsequent successful grant with no fullName preserves canonical name
without a second name command.

The signed local journey uses real local Auth and PostgreSQL60332 with the
current candidate API in a TestClient. It exercises name outage/retry,
reconstructed-client readback, later edit/clear preservation, extra user-id
refusal, deletion admission and zero fake provider calls. Its own users and rows
are removed by the existing fixture. No standalone API service or Auth
configuration replacement was needed.

## Native callback and model proof

An independent `git archive` of the tested source changes only the debug
AppleSessionHarness and its synthetic loopback server, and adds two test files.
All production owners, including NativeProviderSignIn, ProfileAuthModel,
SessionController, CredentialStorage and AppleNameIntent, match the tested
candidate byte for byte. [Provenance](provenance.json) records the complete
tracked iOS source comparison; [diagnostic patch](independent-harness.patch)
preserves the exact copied changes.

The unchanged production callback and model compiled in the simulator build.
The callback's Foundation formatter and synchronous prepare-before-Task order
were checked against the actual source. The temporary UI controls exercise the
actual model and controller through the production Swift SDK and transport,
with a fake successful Apple grant and typed credential checker on loopback59920.
They do not instantiate an actual ASAuthorizationAppleIDCredential or authorize
an Apple provider session.

The UI journey prepares the formatted name synchronously, reads only its own
Keychain pregrant item, and verifies exactly four durable fields: id, subject,
displayName and createdAt. This happens before the grant button starts its Task.
No token or authorization code is stored in that pregrant item. With supplied
given/middle/family components, Foundation's default formatter produced
`María 王`; the test requires canonical profile equality with that exact Unicode
formatter result, rather than claiming every raw component is preserved.

The fake code-capture command fails503, and the first name command fails503.
The actual model remains authenticated with a pending name command. A retry
returns the canonical formatted name, and a separate-process relaunch reads the
same name. [Before counters](ui-before.json) are name 0/code 0/grant 0;
[after counters](ui-after.json) are name 2/code 1/grant 1. Neither grant nor one-time
code is replayed on name retry or relaunch. Four screenshots show pregrant
durability, the outage, canonical retry and canonical relaunch.

## Findings resolved by the source author

The original `07f768f28be6f900b1a3d2e7b242bcdbad25d93a` failed compilation before
any tests: the new XCTest class's stored property `name` conflicts with inherited
XCTest's name property. [Original output](07f768-compile-failure.log) is retained.
The actually preceding commit `8d60ff234` compiled and passed its 139-test package
with four opt-in skips in 10.424 seconds. The author published
`060a03f883f08fccdb613ee65343a8296a4793d7`, renaming that fixture property and its
references only. [Rename diff](fixture-rename.diff) shows unchanged assertions.

At 060, all 15 new cases passed, but the existing
testDeleteFailureRemainsPendingUntilLocalCleanupSucceeds failed. The focused
baseline passed 1; focused060 failed 1. The new pregrant deletion ran before
durable pending-credential storage, so a temporary Keychain removal failure
prevented the established retirement journal from owning recovery. The author
published a6, moving that one deletion after pending storage and before session
removal. The unchanged existing regression, all 15 new cases, full 154 suite and
the independent 3 cases passed on that final source. Baseline/failure outputs
are retained and are not counted as final acceptance.

One independent UI harness preparation failed to compile because DeviceKeychain
is internal to ArgusSession. Only the copied diagnostic was corrected to read
its own pregrant item through Security. No product API was widened, and no
candidate source was edited. The final actual-model UI run passed.

## Commands and boundaries

Full and focused package runs used:

```sh
CLANG_MODULE_CACHE_PATH=/private/tmp/cuadrao-combined-clang-cache \
SWIFTPM_MODULECACHE_OVERRIDE=/private/tmp/cuadrao-combined-swift-cache \
swift test --package-path ios/Packages/ArgusSession \
  --scratch-path /private/tmp/cuadrao-apple-session-swift \
  --cache-path /private/tmp/cuadrao-session-spm-cache \
  --disable-sandbox --disable-automatic-resolution
```

The focused filter was
`AppleNameInitializationTests|testDeleteFailureRemainsPendingUntilLocalCleanupSucceeds`.
The independent copy used the same command with package path
`/private/tmp/cuadrao-apple-name-independent/ios/Packages/ArgusSession` and filter
`IndependentAppleNameBoundaryTests`. The provider configuration command was
`python ios/DesignPreviewTests/run_native_provider_config.py`.

The signed current source command was
`python -m pytest tests/test_apple_name_api_postgres.py -q --no-cov -o addopts=`
with `PYTHONPATH=web:src:.`, dotenv disabled and private local configuration.
The published sanitized recipe reads the database connection from private
api-env.json instead of retaining its password here.

The UI command used copied cwd, `xcodebuild test -project
ios/ArgusFoundation.xcodeproj -scheme ArgusFoundation -configuration Debug`,
destination `platform=iOS Simulator,id=FEB9FD84-9606-4E56-AD07-AAA14B7AF72A`,
derived data `/private/tmp/cuadrao-apple-name-xcode`, cloned packages
`/private/tmp/cuadrao-apple-session-xcode-packages`,
`-disableAutomaticPackageResolution -parallel-testing-enabled NO`,
`-only-testing:ArgusFoundationUITests/IndependentAppleNameUITests`, result
`/private/tmp/cuadrao-apple-name-ui-fixed.xcresult`,
`CODE_SIGNING_REQUIRED=NO`, bundle `local.argus.apple-name-independent`.
The owned simulator was iPhone 17 Pro/iOS26.5. Normal provider flags were not
activated. No provider authorization, paid/model call, phone, hosted change,
identity/email merge, branch write, push, main modification or deployment
occurred.

## Warnings, cleanup and publication

The final native build has the same weak auth-capture compiler warning observed
in the preceding combined-native logs. AppIntents metadata extraction reports
no framework dependency, also observed previously. Package runs report
inaccessible sandboxed user-level Swift configuration/security caches and use
explicit owned caches. The final UI result has no runtime warnings.

[Cleanup](cleanup.json) confirms own port 59920 free, own simulator deleted, signed
test users absent, candidate clean and root Auth/PG healthy. This run did not
change root Auth configuration, start a standalone real API, stop the root DB,
or touch a foreign process, simulator, Preview installation or phone.
Text evidence was scanned for actual local credential values; none were found.
Raw xcresult containers, private config and Auth credentials are not included.

The captain must commit or attach this evidence folder before a ready claim.
Physical Apple authorization/credential state, #864 landing and reconciliation,
exact-head CI and any later activation remain separate gates.
