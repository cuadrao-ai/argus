# Financial loop device and hosted preparation

Observed September 29, 2026, from integration
`fcbb70cc2899ca6a05c03c49316e9a4e4cbf5333`.
The [execution manifest](../specs/argus-execution-board.md) owns assignments and
progress. This report records access evidence and the scoped release actions.
It does not authorize provisioning, migration, deployment, or spending.

## Observed access

| Check | Result | Consequence |
| --- | --- | --- |
| `security find-identity -v -p codesigning` | Zero valid identities | No signed artifact can be produced yet |
| `xcrun devicectl list devices --timeout 20` | A physical iPhone 15 is known, but unavailable | Connect, unlock, and trust the Mac before installation; OS and Developer Mode remain unverified |
| `xcodebuild -version` | Xcode 27.0, build 27A266a | Toolchain is available |
| Supabase project and organization metadata | Existing Argus project is healthy, Postgres 17.6; organization plan is Free | Reuse this project and current plan |
| Supabase migration metadata | Latest recorded migration is `20260914120000`; `20260928200000_financial_accounts_first_slice` is absent | The account schema still needs an approved hosted migration |
| Read-only schema lookup | `financial_accounts`, `financial_records`, and `financial_record_revisions` are absent | This is a schema gap, not merely missing migration bookkeeping |
| `GET https://api.arguschat.ai/health` | HTTP 200, `healthy` | API is reachable, but health does not identify its deployed commit |
| `render services --output json` | CLI credential expired | Live service IDs, revisions, flags, and capacity remain unverified until operator login |

The initial sandboxed CoreDevice query timed out. The unsandboxed read-only query
returned the device inventory above. No customer rows, credentials, or session
tokens were read. No Apple account, device, or hosted settings were changed.

## Native internet login candidate

The new exact document is `/auth/native-captcha` on the existing web app.
The proposed hosted URL is `https://arguschat.ai/auth/native-captcha`.
It has not been deployed or verified over the internet.

The document calls the existing `acquirePasswordAuthCaptchaToken` helper and
existing `NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY`. It returns only
`{type: "token", token}` or `{type: "error"}` to the native `argusCaptcha`
handler. It never receives a password, signs in, adopts a session, or stores a
token. Ordinary browser visits without the native handler acquire nothing.
Cancellation aborts the shared challenge and suppresses late delivery.

The native reader retains its exact document URL, main-frame, origin, and token
validation. Existing `/api/v1/auth/login`, Supabase validation, Keychain session
storage, and web password recovery remain the owners of their current behavior.
There is no new auth architecture or CAPTCHA bypass.

The existing root providers initialize only theme and localization for this
route. The production browser check observes no guest, auth, or session API
request. The current CSP restricts images and permits the existing Cloudflare
script and challenge frame. The dedicated route denies embedding through
`X-Frame-Options: DENY`, sends `Referrer-Policy: no-referrer`, and requests
`Cache-Control: no-store`. Its JavaScript also requires the top-level window.
No CORS or native frame allowlist expansion is needed.

An API-hosted page was rejected because it would duplicate the web CAPTCHA owner
and could require another approved Turnstile hostname. The additive web route
preserves the existing production web. The local loopback test page under
`ios/scripts/auth` must never be deployed as this bridge.

## Prepare a signed installation after approval

Use the founder's existing Apple team. Recommend direct Xcode development
installation for the first phone checkpoint, with one stable bundle identity.
If an existing paid team is available, the same identity can later support a
private TestFlight update route. Do not enroll, purchase, or create another team.
`ai.arguschat.argus` is a proposed identity only; verify availability and obtain
approval before registering it.

Apple permits personal-device testing with a Personal Team, but its provisioning
expires after seven days and requires rebuilding and reinstalling. It can prove
the first internet loop without a paid membership, but does not provide durable
unattended updates. See [Apple's developer account guidance](https://developer.apple.com/help/account/basics/about-your-developer-account).

The founder action is to connect and unlock the iPhone, trust the Mac, and make
the intended Apple account/team available in Xcode. The next approval identifies
the team, stable app ID, device registration, certificate/profile creation or use,
and installation. Neither account login nor this preparation approves those writes.

After that approval:

1. Copy `ios/Config/Device.local.xcconfig.example` to the ignored
   `ios/Config/Device.local.xcconfig`.
2. Set only the approved team, app ID, public endpoints, and public Supabase key.
   Use HTTPS origins and the exact bridge URL. Keep passwords and session tokens
   out of build settings. Enable auth only for the approved hosted candidate.
3. Build the selected candidate on the approved physical device. Use Xcode's
   automatic provisioning only after the specific provisioning grant.
4. Install over the existing app with the same identity. Confirm Keychain
   persistence and update behavior. Do not uninstall to work around a failure.
5. Disconnect the Mac and use cellular or unrelated Wi-Fi for acceptance.

Without the ignored device file, the project still resolves to simulator-only,
`local.argus.foundation`, its existing ad-hoc Keychain entitlement, and auth off.
With the device file, Xcode derives the entitlements from the approved profile
instead of using the simulator's unprefixed application identifier.

## Hosted approval packet that remains to complete

Restore read-only Render CLI access first. Record the live API and web commit
SHAs, service IDs, build settings, and financial flag value. Do not equate the
integration SHA with a deployed SHA. Do not deploy integration wholesale.

| Action requiring approval | Concrete candidate and precondition | Rollback |
| --- | --- | --- |
| Deploy the additive CAPTCHA adapter to existing `argus-app` | Build from its actual deployed baseline plus only the bridge, abort propagation, headers, and tests. Retain its existing public site key. Verify existing login/recovery and exact route response. No replacement web changes | Redeploy the recorded previous web SHA; native login reports unavailable while existing web login remains intact |
| Apply financial schema migrations to the existing Supabase project | Financial owner supplies the exact reviewed migration list and compatibility checks. Compare the candidate against actual hosted schema. Take an authorized backup and verify restore before writing. No blanket migration push | Disable financial writes and retain records/schema; use a reviewed forward repair. Do not drop tables or restore over new financial data |
| Deploy the compatible financial API candidate to existing `argus-api` | Captain supplies exact candidate, required migrations, focused regression proof, and previous deployed SHA. Keep account capability off until schema and route smoke pass. Confirm capacity within existing setup | Disable financial capability and redeploy compatible previous API SHA; retain durable records |
| Enable the approved native build against the hosted candidate | Use the same existing Supabase project/user and approved API/web origins. The final app configuration must not contain test keys or loopback endpoints | Install the prior compatible signed build with the same identity; do not erase Keychain or the app container |

Unapplied unrelated migrations are not automatically part of this batch. Any
production baseline incompatibility must be resolved in the minimal compatible
candidate before asking for deployment approval. Provider calls and new paid
infrastructure are not part of this packet.

## Local proof and limits

- An unsigned generic iOS build succeeded with the opt-in configuration and an
  explicitly local validation identity. The temporary override was removed.
  This proves device compilation, not provisioning, installation, or Keychain
  behavior on the phone.
- The default build settings were read back after cleanup. Simulator support,
  local identity, simulator entitlements, and auth-off defaults were preserved.
- The narrow bridge and existing auth/CAPTCHA suite passed 27 tests.
- The production web build and focused ESLint checks passed.
- The isolated browser suite passed success, error, ordinary-browser, and
  pending-document-close scenarios. External requests were intercepted by a
  synthetic Turnstile response. No real provider token or hosted login was used.
- Standalone repository-wide `tsc --noEmit` reports existing Bun test declaration
  and unrelated test errors. The Next production build passed its own checks.

Repeat the browser verification from `web/` with a local synthetic build:

```sh
NEXT_PUBLIC_ARGUS_TURNSTILE_SITE_KEY=synthetic-native-captcha-site-key \
NEXT_PUBLIC_ARGUS_API_URL=https://api.arguschat.ai/api/v1 bun run build
bun test ./__tests__/native-captcha.test.ts ./__tests__/guest-captcha-ux.test.ts ./__tests__/auth-captcha-confirmation.test.ts
bunx playwright test --config e2e/native-captcha.playwright.config.ts
```

That output is a local test artifact. Never deploy a build with the synthetic
site key. Hosted acceptance still requires the existing production key, actual
WKWebView challenge, existing-user login/refresh/reopen, and the financial loop
on the physical iPhone away from the development computer. No phone outcome is
accepted by this report.
