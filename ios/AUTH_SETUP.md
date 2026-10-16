# Native registered sessions

Authentication is **off by default**. Profile can connect to existing Argus
signup/login and `/me`. The [account continuation](ACCOUNTS_SETUP.md) reuses that
same session for canonical Home, Accounts, expense corrections and balance checks.
Argus, Plan and Search remain local sample destinations in this bounded build.
The auth adapter adds no guest bootstrap, calculations or provider calls.

## Configuration

`Config/Development.xcconfig` owns defaults; ignored `Config/Local.xcconfig`
accepts the public keys listed in its example. API, Supabase and web URLs are
root origins, without `/api/v1`. CAPTCHA is an exact bridge URL. HTTPS is required
except loopback HTTP for local development. Escape URL slashes in xcconfig as
`https:/$()/example.test` because `//` starts a comment.

Enable `ARGUS_AUTH_ENABLED = true` only for an explicitly allocated environment.
The anon/publishable key is public. Never add passwords, service-role keys or
session tokens. Disabled mode creates no client or requests. Production endpoints,
CAPTCHA hosting, identity, signing team and callbacks remain unapproved.

The simulator uses an **ad-hoc signature with no account/team**, with
`application-identifier` derived from the replaceable local bundle identity.
This lets Keychain work; an unsigned simulator executable fails with -34018.
The default project configuration remains simulator-only. The opt-in
[device configuration](../docs/reports/financial-loop-device-preparation.md)
requires approved signing access.

## Native Apple and Google sign-in

Both are **off by default** and sit on top of `ARGUS_AUTH_ENABLED`. Debug builds
can expose the buttons on the connected create-account and sign-in screen above
"Continue with email". Google also requires Apple and valid callback configuration.

`Config/Release.xcconfig` forces both flags off after ignored local overrides.
The Release runtime disables both providers even if command-line build settings
force the flags on. Activation requires a reviewed code change after the remaining
[#800 gates](https://github.com/lagarcess/argus/issues/800) are accepted. Email
entry remains available.

| Key | Value |
| --- | --- |
| `ARGUS_APPLE_SIGN_IN_ENABLED` | `true` to show the system Sign in with Apple button in Debug |
| `ARGUS_GOOGLE_SIGN_IN_ENABLED` | `true` to show the official Google button in Debug, when Apple is also enabled |
| `GOOGLE_SIGN_IN_IOS_CLIENT_ID` | The iOS OAuth client, `<number>-<id>.apps.googleusercontent.com` |
| `GOOGLE_SIGN_IN_WEB_CLIENT_ID` | Optional: the web OAuth client Supabase also lists |
| `GOOGLE_SIGN_IN_IOS_URL_SCHEME` | The iOS client's reversed id, `com.googleusercontent.apps.<number>-<id>` |

All are public identifiers; no secret belongs in the app. These sign-in clients
are separate from the Gmail source's `GOOGLE_OAUTH_CLIENT_ID`; never reuse it here. The Google button stays
hidden unless the URL scheme matches the client id, because Google Sign-In crashes
the app when its callback scheme is missing.

- **Apple** uses `AuthenticationServices` with scopes name and email and a SHA-256
  hashed nonce. It needs the Sign in with Apple capability on the App ID and the
  entitlement, which the default simulator build deliberately doesn't carry: a
  build that claims an entitlement its App ID lacks fails to sign. After the
  capability is enabled, use `CODE_SIGN_ENTITLEMENTS = Config/SignInWithApple.entitlements`
  in the ignored `Device.local.xcconfig` (see its example) and test on a device.
- **Google** uses GoogleSignIn-iOS **9.2.0** (pinned in the project) with the same
  nonce pattern, then clears Google's own on-device sign-in state. Native ID-token
  sign-in stores no Google refresh token anywhere, so account deletion has nothing
  to revoke at Google. Apple revocation stays required.
- Both exchange the ID token through Supabase Auth (`signInWithIdToken`) and land
  in the same session path as email. The private-alpha allowlist still applies at
  `/me`; a refused account is signed out at once.
- After Apple sign-in, the app sends Apple's one-time authorization code to
  `POST /api/v1/auth/apple/authorization-code` so account deletion can revoke the
  Apple tokens (Guideline 5.1.1(v)). The server keeps capture off unless
  `ARGUS_APPLE_REVOCATION_CAPTURE_ENABLED` is set; sign-in never depends on it.

### Provider setup

`<bundle-id>` is the approved App ID (today's `local.argus.foundation` is a
placeholder), `<ref>` the Supabase project ref and `<web>` the web origin.
**N** means native iOS needs it, **W** web only.

- **Apple Developer.**
  - **N:** Identifiers → `<bundle-id>` → enable Sign in with Apple.
  - **N:** Keys → new key with Sign in with Apple for `<bundle-id>`. Download the
    `.p8` once and note the Key ID and Team ID. These go to the API environment
    (`ARGUS_APPLE_TEAM_ID`, `ARGUS_APPLE_SIGN_IN_KEY_ID`,
    `ARGUS_APPLE_SIGN_IN_PRIVATE_KEY`, `ARGUS_APPLE_BUNDLE_ID=<bundle-id>`) for
    token revocation, never to the app.
  - **W:** Services ID (for example `<bundle-id>.web`) with Sign in with Apple:
    domain `<ref>.supabase.co`, return URL `https://<ref>.supabase.co/auth/v1/callback`.
- **Google Cloud.**
  - **N, W:** OAuth consent screen with app name, support email, privacy and terms
    links and the `openid`, `email`, `profile` scopes, published to production.
  - Create new sign-in clients; don't reuse the Gmail source's web client
    (`GOOGLE_OAUTH_CLIENT_ID`).
  - **N:** OAuth client of type iOS for `<bundle-id>`. It gives
    `GOOGLE_SIGN_IN_IOS_CLIENT_ID` and `GOOGLE_SIGN_IN_IOS_URL_SCHEME`.
  - **W:** OAuth client of type Web with JavaScript origin `<web>` and redirect URI
    `https://<ref>.supabase.co/auth/v1/callback`. Its id may also be set as
    `GOOGLE_SIGN_IN_WEB_CLIENT_ID`.
- **Supabase → Authentication → Providers.**
  - **Apple, N:** enable, Client IDs `<bundle-id>`. **W:** add the Services ID
    (comma-separated) and a secret key JWT generated from the `.p8`, renewed
    within six months.
  - **Google, N:** enable, Client IDs `<web-client-id>,<ios-client-id>` (web first
    when web is used), "Skip nonce check" off. **W:** the web client secret.
  - **W:** URL Configuration with Site URL `<web>` and the web callback in Redirect URLs.

## Session behavior

`Packages/ArgusSession` owns cookie-free transport, device-only Keychain storage
and identity. Official Swift Auth SDK 2.55.2 is pinned, with resolved dependencies.
Argus owns login/signup policy and CAPTCHA; the SDK owns adoption/refresh/revoke;
`/me` owns displayed identity. Credentials are scoped to app and environment.

Failed sign-out remains pending and blocks another login until retry settles
revocation and cleanup. Unexpected anonymous SDK identity is retained and native
registration/switching blocked pending an accepted guest-transfer contract.
Confirmation-required signup shows email instructions; generic resend is absent.
Forgot password opens web `/auth/forgot-password`: request and finish in that
same browser, then sign in freshly in the app. No native recovery or callbacks.
PR #726 remains evidence, not production probe code.

## Local acceptance

Prerequisites: Xcode/iPhone Simulator, Docker, Supabase CLI, Python3.12, Poetry,
Bun. Reserve ports first: API58400, Supabase58401, DB58402, mail58403,
SMTP58404, CAPTCHA58405, internal58407–58411, and web127.0.0.1:3001.
The web port is required by the existing HTTP recovery allowlist. Do not change
shared config or stop another worker's listeners. Run from repository root:

```bash
uv venv --python 3.12 .venv
poetry install --only main --no-root
(cd web && bun install --frozen-lockfile)
python3 ios/scripts/auth/local_stack.py configure
python3 ios/scripts/auth/local_stack.py start
python3 ios/scripts/auth/local_stack.py seed
```

The helper copies canonical migrations/config into ignored scratch and creates
two synthetic accounts, mode600 `ios/.build/auth-local/client.json` and public
`Config/Local.xcconfig`. Existing fixture/config is not overwritten. No root
`.env` or web `.env.local` may be present. In separate terminals:

```bash
python3 ios/scripts/auth/local_stack.py api --python "$PWD/.venv/bin/python"
python3 ios/scripts/auth/bridge.py
python3 ios/scripts/auth/local_stack.py web
```

Only this local stack has 60-second JWTs and Cloudflare public always-pass test
keys. Native still acquires a WK widget token. The unchanged web dev flow uses
its canonical local QA CAPTCHA token. Neither proves production CAPTCHA.

```bash
swift test --package-path ios/Packages/ArgusSession
ARGUS_SESSION_LIVE_CONFIG="$PWD/ios/.build/auth-local/client.json" \
  swift test --package-path ios/Packages/ArgusSession --filter LiveSessionTests
xcrun simctl list devices available
python3 ios/scripts/auth/run-ui.py <lane-owned-iPhone-UDID>
TEST_RUNNER_ARGUS_UI_TESTS_ALLOW_PREVIEW_BUILD=true SIMULATOR_ID=<UDID> ios/scripts/verify.sh test ARGUS_AUTH_ENABLED=false
```

Live package tests use four login attempts plus one signup; native journey uses
one login; browser recovery uses two. CAPTCHA-only checks need no account:

```bash
python3 ios/scripts/auth/run-ui.py <UDID> --captcha-mode hold --only ArgusFoundationUITests/AuthJourneyUITests/testCaptchaCancellationKeepsEntry
python3 ios/scripts/auth/run-ui.py <UDID> --captcha-mode fail --only ArgusFoundationUITests/AuthJourneyUITests/testCaptchaFailureShowsRetryableEntry
python3 ios/scripts/auth/run-ui.py <UDID> --only ArgusFoundationUITests/AuthUITests
```

Only the loopback bridge reads this test mode; native code has no bypass. Respect the server's eight-attempt/IP/
ten-minute limit. Do not relax it to obtain a pass. UI credentials are written to
a temporary mode600 `.xctestrun`, then removed. Passwords enter a local-only,
expiring clipboard, cleared afterward, rather than a logged `typeText` action.
Raw logs/results stay ignored. Promote only sanitized screenshots/summaries.

Browser recovery helper commands and source provenance accompany the durable
recovery evidence. Fresh snapshots must supply current Playwright element refs.
No native-account fixture is reused for password reset.

Stop own terminal processes with Ctrl-C, then
`python3 ios/scripts/auth/local_stack.py stop`. This stops only `ios-auth-8be2`
and retains its local data. Shut down only assigned simulators; never erase a
shared device or stop unrelated containers. Local synthetic evidence is not
hosted readiness. Guest transfer, resend and callbacks remain separate work.
Financial wiring has its own [setup and evidence](ACCOUNTS_SETUP.md).
See the [lane spec](../docs/superpowers/specs/2026-09-28-ios-auth-session.md)
for ownership and exact integration/design/auth reference commits.
