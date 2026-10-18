# Argus iPhone foundation

A SwiftUI foundation, offline by default, with Home, Accounts, Argus, Plan and Search in
the approved order. It runs as **Cuadrao**. Navigation, local search and
Light / Dark / System appearance work. With authentication disabled, financial figures are immutable display fixtures.
With authentication configured, Home and Accounts use canonical server records. An optional, default-off
registered-session adapter connects existing Argus authentication. See
[native auth setup](AUTH_SETUP.md) and [financial account setup](ACCOUNTS_SETUP.md)
for configuration and verification. With native authentication configured,
Accounts establishes balances, records and corrects expenses, and checks balances.
Home reads the same canonical position and recorded-spending totals;
the server feature flag remains authoritative. No financial records are stored
in app preferences. Connected Household sharing uses the default-off canonical
backend; see [Household setup and tests](HOUSEHOLD_SETUP.md). Calculations, voice, monitoring and financial-provider
integrations remain outside this client.

## Run in Simulator

1. Install Xcode with an iOS Simulator runtime through **Xcode > Settings >
   Components**. Select that Xcode in **Settings > Locations > Command Line Tools**.
   This project targets iOS 17 or newer and requires an iOS 26.4 or newer build
   SDK for the guarded Declared Age Range regulatory symbols. CI uses Xcode 26.6;
   local age-gate acceptance uses Xcode 27.1 / iOS 27.0 Simulator. The deployment
   floor is not a claim that every older runtime was tested.
2. Open `ArgusFoundation.xcodeproj`, select the shared **ArgusFoundation** scheme,
   select an iPhone simulator and press Run. No account or development team needed.
3. For command-line verification from repository root:

   ```bash
   xcrun simctl list devices available
   SIMULATOR_ID=<iPhone-UDID> ios/scripts/verify.sh build
   SIMULATOR_ID=<iPhone-UDID> ios/scripts/verify.sh test
   ```

The test action also builds. Results and logs go to ignored `ios/.build/results/`;
set `RESULT_DIR` to choose another output directory. Extra Xcode options may
follow the action, for example `-only-testing:ArgusFoundationUITests/FoundationUITests/testNavigationAndHeaderReturn`.
Tests run serially on the selected simulator. Foundation tests use local fixtures;
auth and financial journey tests are separately opt-in and require the isolated
synthetic stack. They write synthetic financial records, without provider calls.

To install and launch after a command-line build (substitute your simulator ID):

```bash
xcrun simctl boot <iPhone-UDID> # omit if already booted
xcrun simctl install <iPhone-UDID> ios/.build/DerivedData/Build/Products/Debug-iphonesimulator/ArgusFoundation.app
xcrun simctl launch <iPhone-UDID> local.argus.foundation
```

Use a separate simulator when other work is active. The default configuration
supports Simulator only, device family 1 (iPhone), no Catalyst or iPad target.
The opt-in [device preparation](../docs/reports/financial-loop-device-preparation.md)
uses a separate configuration after the founder approves signing access.
A local ad-hoc signature enables simulator Keychain without a signing account.
Production bundle identity, team, provisioning, physical
device distribution and release OS support remain unresolved.

## Local configuration and future owners

`Config/Development.xcconfig` owns development settings. Its
`local.argus.foundation` bundle identifier is a replaceable simulator placeholder.
Optional `Config/Local.xcconfig` is ignored; copy the neighboring example to
give a second installation a different local identity. Changing identity creates
a separate preference container. Only public endpoint configuration belongs in these files; never put passwords,
service-role keys, access tokens or refresh tokens in app configuration.

The [registered-session continuation](AUTH_SETUP.md) uses the official Swift Auth
SDK and existing Argus endpoints. #726 remains evidence, not application code.
The adapter keeps sessions in a device-only Keychain, never in app preferences.
Financial rules and calculations remain backend responsibilities.

## Reference and shared owners

The committed [lane spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-28-ios-foundation.md)
defines ownership and acceptance. The experience reference is
[PR #727 at a1c294319a2c047623b9bbe5bedd36155d2e931d](https://github.com/lagarcess/argus/tree/a1c294319a2c047623b9bbe5bedd36155d2e931d/docs/reports/evidence/mobile-design-lock-2026-09-28),
archive `mobile-2026-09-28`, SHA-256
`c55e565aa142e38eec61b570510af1c4c2cb9629c24f3ce2d01387639f0ea0e6`.
The latest inspected reference is `d7faac770369242436a5e108bb557ba0bae893d3`:
one review correction removes the contradictory universal-pill instruction;
the archive is unchanged. That PR was open and in review at lane start. Its canonical documentation was
neither copied nor merged into this lane. The archive's finance JavaScript is
not used. The locked template owns interactions; this lane adds native shell
behavior and explicitly labeled sample destinations within its assigned scope.

The historical account-only continuation inspected the now-merged #727 at exact head
`f0a64ffb9d70ce5b82491cf8e1803bb8a6ec7431`; the same locked archive remains
the experience reference. Its recovered implementation is described by the
[account client spec](https://github.com/lagarcess/argus/blob/651870a54be4e5506dbb38f3902fef1a97eef8df/docs/superpowers/specs/2026-09-29-ios-financial-accounts.md).

Shared semantic tokens and controls live in `ArgusFoundation/`. The shell owns
destination selection; individual views own transient presentation state.
Appearance is the only non-credential app preference persisted by this foundation, using
UserDefaults through SwiftUI AppStorage. Removing the app resets it. System
appearance follows the OS, while Light and Dark override it. Appearance does
not synchronize with a server profile. Static copy is localized for English and
Latin American Spanish using native resources and the device language.

Bundled fonts derive from the existing `web/app/fonts/` WOFF2 sources under their
included SIL Open Font licenses. Static Inter 400/500 and Space Grotesk 500 TTFs
are committed so app builds require no download/conversion. To regenerate them
after an intentional canonical font change, create a temporary Python environment,
install `fonttools==4.65.0` and `brotli==1.2.0`, and run
`python ios/scripts/derive_fonts.py`. The Argus mark derives from the existing
angular A geometry; no replacement logo is designed here.

## Acceptance and evidence

The UI tests cover tab order/selection/targets, header sheets and return, sample
disclosure, all appearance choices across process relaunch, retained search state,
keyboard, Spanish, enlarged Dynamic Type and accessibility labels/traits/targets.
Screenshots attach to the `.xcresult`. Manual simulator checks additionally inspect
actual theme resolution, two iPhone sizes, safe areas and layout.

Durable acceptance captures and their exact source/head boundaries live in
[`docs/reports/evidence/ios-foundation/`](../docs/reports/evidence/ios-foundation/).
Simulator accessibility checks are a basic foundation check; they do not claim
physical-device VoiceOver, production financial journeys or backend acceptance.

Connected financial acceptance is owned by the current
[execution manifest](../docs/specs/argus-execution-board.md), linked to the MVEE.
See [financial setup](ACCOUNTS_SETUP.md) for the repeatable simulator and model
checks. A simulator pass does not satisfy physical-iPhone internet acceptance.

## UI tests need the Cuadrao configuration

UI tests run only against a build that sets `ARGUS_AUTH_ENABLED = true`. Without
it the app builds as the legacy foundation preview, not Cuadrao. The ignored
`Config/Local.xcconfig` sets it. `python3 ios/scripts/auth/local_stack.py seed`
writes that file for the local stack (see [Local acceptance](AUTH_SETUP.md#local-acceptance)).

The UI test bundle reads the same build setting. If the value is not `true`, every
UI test fails before setUp and launches no app. Each failure names
`ios/Config/Local.xcconfig` and the setup command. The check runs whatever starts
the tests: Xcode, `xcodebuild`, `scripts/verify.sh` or `scripts/auth/run-ui.py`.
A run that passes `ARGUS_AUTH_ENABLED=false` on the command line stops the same
way. To fix a stopped run, create the file and run build-for-testing again.

A deliberate offline run, such as the auth-disabled design pass, sets
`TEST_RUNNER_ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD=true`. The default stays strict.

## Localization foundation

`ArgusFoundation/Resources/Localizable.xcstrings` owns the existing 843 keys
and their English and Latin American Spanish values. The catalog preserves
baseline wording, including existing untranslated copy. The project development
region is `es-419`. This sets the bundle fallback language. It does not translate
hardcoded Swift strings or override an explicit supported device language.
`InfoPlist.strings` remains a separate resource.

`python3 ios/scripts/localization_guard.py` checks catalog structure and warns
about direct, single-line UI literals that have not moved into the catalog.
These warnings return exit code zero during the foundation phase. Invalid
catalog or registry inputs return a nonzero exit code. The scan is deliberately
partial. It does not prove that every user-visible string is localized.
The build and test wrapper runs it before Xcode.

`ios/scripts/localization_noncopy.json` starts empty. Later slices can add exact
`path`, `literal`, and `reason` entries for technical values found by the scan.
Run the CLI tests with
`python3 -m unittest discover -s ios/scripts -p test_localization_guard.py -v`.
