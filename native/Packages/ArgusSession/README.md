# ArgusSession

Registered-session ownership for the iPhone app. The package depends on the
`Auth` product from official `supabase-swift` **2.55.2**; `Package.resolved` pins
transitive dependencies. It contains no SwiftUI, financial rules, guest entry,
auth-account management endpoints, CAPTCHA acquisition or recovery callbacks.
It transports the landed financial-account API without storing financial data.

## App boundary

Create one `SessionController` per app session. Its constructor makes no network
request. Call `restore()` explicitly when auth is enabled. Configure API and
Supabase **origins**, with no `/api/v1` or `/auth/v1` suffix. HTTPS is required
except for loopback development. Public publishable/anon keys are accepted;
secret/service-role keys are rejected. Keep development values in the app's
ignored configuration, never in this package.

Public methods are `snapshot`, `requestCredentialRevalidation`, `restore`, `login`, `signup`, `signIn(with:)`,
`profile`, `signOut`, `retryPendingSignOut` and `captureAppleAuthorizationCode`. Signup accepts an optional trailing `displayName`.
`SessionSnapshot` contains a phase, the canonical Argus `/me` profile, an optional
linked `AppleIdentity` and an account revision. It never exposes credentials.
The phases are `signedOut`, `authenticated`, `signOutPending`,
`unsupportedAnonymousSession`, `credentialValidationRequired` and
`reauthenticationRequired`.

Auth mutations are serialized; overlapping mutations return `busy`. Profile
reads may run concurrently. Before every retry or delivery, their original
account epoch must still be current. A stale request cannot refresh, deliver
another account's profile, or write/delete that account's SDK storage.

## Native Apple and Google sign-in

`signIn(with:appleAuthorizationCode:)` returns a `ProviderSignInOutcome` containing
the session snapshot and optional typed Apple capture result. It takes an Apple or Google ID token from the
app's native sheet plus the `SignInNonce` used for it. The nonce's SHA-256 hex
digest goes to the provider and the raw value only to Supabase Auth's `id_token`
grant, which runs on an isolated in-memory SDK client. The issued tokens then take
the same journaled adoption as email login: pending journal, `setSession`, `/me`.
If Argus refuses the new session (for example the private-alpha allowlist at
`/me`), it is revoked at once; a failed revoke stays pending like any sign-out.
Provider 4xx errors surface as `rejected` with a bounded code, 5xx as
`unavailable`. `captureAppleAuthorizationCode` posts Apple's one-time code to
`POST /api/v1/auth/apple/authorization-code` for revocation at account deletion;
the composite sign-in awaits one ordinary attempt. Capture produces a separate visible
result while ordinary session invalidation rules still apply; a consumed code is never replayed. The server answers a plain 404 while capture is off and
`409 apple_identity_mismatch` when the code belongs to another Apple ID.

## Credential and error behavior

- Login/signup call existing Argus endpoints with a caller-supplied fresh CAPTCHA
  token. A confirmation-required signup does not log in automatically.
- Both Argus and SDK requests use an ephemeral, cookie-free transport. Redirects
  are rejected. Credentials are namespaced by the API/Supabase origin pair.
- SDK credentials use device-only Keychain storage. Writes update existing items
  before attempting an insert. The adapter detects SDK-swallowed storage errors.
- The SDK owns refresh. An authenticated 401 permits one logical refresh and
  request retry; another 401 or a refused refresh ends the usable session. A
  refused refresh without definitive revocation proof remains pending cleanup.
  Transport/5xx errors remain retryable. SDK refresh/logout requests independently have up to two internal
  transient retries in the pinned release.
- Sign-out journals pending revocation before local deletion. An isolated SDK
  client refreshes pending credentials, persists rotation, and revokes locally.
  Only observed logout HTTP success or terminal rejected-refresh proof clears
  the pending marker. SDK-suppressed logout 401/403/404 alone is insufficient.
- Pending revocation blocks entry and retries on restore or explicit retry. If
  Keychain refuses a write, issued credentials remain in memory and the failure
  stays visible. No application can promise crash-durable recovery while the OS
  refuses every durable write; a storage preflight reduces this window.
- An existing anonymous SDK session is preserved without network activity and
  blocks registration/account replacement. Guest transfer needs its own server
  contract. There are no guest endpoint calls in this package.

Only bounded `SessionFailure` values leave the package. SDK logging is disabled;
never log a session, request body, tokens or CAPTCHA values in callers. Recovery
belongs to the app's external browser flow, with no native verifier transfer.

## Tests

From the repository root:

```bash
swift test --package-path native/Packages/ArgusSession
```

Ordinary tests inject only storage/HTTP boundaries and exercise the actual SDK.
They cover configuration, cookie policy, redirects, identity binding, refresh,
failed persistence, stale requests/storage writes, and pending revocation.

The separately enabled local suite reads the existing synthetic-account fixture:

```bash
ARGUS_SESSION_LIVE_CONFIG="$PWD/ios/.build/auth-local/client.json" \
  swift test --package-path native/Packages/ArgusSession --filter LiveSessionTests
```

It refuses origins outside the lane's loopback ports 58400/58401 and skips when
the environment variable is absent. It uses real Keychain storage and unchanged
local Argus/Supabase: registered login/profile, new-controller restore, old-token
rejection after revoke, account switching, concurrent expiry refresh, invalid
login and confirmation-required signup. It consumes four login attempts and one
signup; coordinate the shared local attempt limit before running. The public
CAPTCHA test token exists only in the test target. Simulator/process-relaunch,
CAPTCHA widget, browser recovery and real-device proof belong to the app lane.

## Financial accounts

The five bounded account methods require `expectedIdentity: SessionSnapshot`
from the displayed authenticated session. UUID account ids cannot inject paths.
The session owner attaches credentials through the same authenticated transport
as `/me`; callers never receive a token. Identity retirement rejects both late
successes and failures, and an old form cannot send under a newly signed-in user.
After a failure, read `snapshot()` and clear UI records/drafts if the session
phase or identity epoch changed. Clear them immediately when initiating sign-out.

`FinancialAccount` and related values preserve decimal amounts and offset dates
as strings, signed minor units as `Int64`, and stored IANA zones unchanged.
Unknown balances retain nil amounts. These are wire types, not a financial cache
or a second owner of accounting rules.

Keep the immutable `CreateFinancialAccountRequest` for uncertain-delivery retries:
its generated UUID key and sorted JSON body remain identical. For PATCH/PUT,
retain the version/revision originally viewed. On conflict or uncertain delivery,
reread explicitly; never auto-upgrade tokens and resubmit. An empty nickname
explicitly clears it; nil omits the edit. Omit unchanged opening amount/date/zone.
Liability GET amounts are signed to the owner, whereas entered write amounts
are positive owed: a date-only debt correction must not replay its GET amount.

Deterministic tests cover precision, unknown/zero, frozen create retry bodies,
both concurrency tokens, bounded errors, one refresh, and retired identities.
Run the separate one-login real-service financial journey only after starting
and reserving the isolated accounts stack:

```bash
ARGUS_SESSION_LIVE_CONFIG="$PWD/ios/.build/accounts-local/client.json" \
  swift test --package-path native/Packages/ArgusSession --filter LiveFinancialAccountTests
```

This proves production Swift transport against real local auth and Postgres:
create/replay, unknown/zero, nickname clearing, initial opening, debt amount and
date-only correction, history, stale save, archive/restore, and new-controller
Keychain restoration with authoritative reread. It does not itself restart the
API process or app process; those acceptance checks belong to the app lane.


Apple credential validation uses the linked subject projected beside `/me.user`.
The projection says which Apple identity is linked to the account, not which
provider created this session. The existing Keychain session value retains the
SDK session fields at the JSON root, with a namespaced versioned provenance
object recording the successful grant method (email, Apple or Google). The pinned
SDK can decode this record directly. Older SDK writes drop that extra object,
leaving a truthful unknown method on the next newer launch. Current SDK refresh
preserves the method only within the same account and epoch, including unknown.
Malformed recognized provenance fails closed. No Apple subject is persisted locally.

Known email and Google sessions remain usable even when an Apple identity is
linked. Known Apple sessions require the canonical profile owner to match the
stored SDK user and the platform credential state to be authorized. Revoked or
not-found credentials retire through the existing pending-sign-out journal.
Platform errors and transferred credentials block product requests while keeping
the stored session available for validation retry. The shared authenticated
transport checks that validation still holds before sending and after responses.

The app admits foreground and revocation signals through
`requestCredentialRevalidation()` before queuing a restore. This actor operation
can hold Apple access while another operation is busy. Each signal invalidates
older checker answers, so an earlier authorized or revoked answer cannot reopen
or retire the session before the queued fresh check. Pending revocation retains
priority; unreadable Keychain state blocks access and also invalidates old checks.
The app's restore queue schedules work, while this session actor owns admission.

Legacy raw SDK sessions have an unknown method. A legacy session with a linked
Apple identity, or a known Apple session without a linked subject, requires the
explicit “Sign out and sign in again” action. It retires the old session through
the existing journal before ordinary sign-in establishes the method. Interrupted
or failed revocation remains pending; no provider is chosen automatically.

Apple code capture is awaited after successful adoption. Its outcome is separate
from sign-in and visible to the person. Each supplied code receives at most one request;
401, uncertain transport failure and server failure never replay that code.
A later attempt requires fresh Apple authorization. Capture does not initialize
a name or link accounts.

Account deletion uses the existing session owner and a token-free per-user vault
journal. `deleteAccount(expectedIdentity:freshAppleAuthorizationCode:)` sends one
confirmed command; `resumePendingAccountDeletion` checks that same command without
SDK refresh or Apple-code replay. Accepted deletion retires interactive proof.
Only a confirmed receipt permits the future app cleanup adapter. Call
`acknowledgeConfirmedAccountDeletion(_:cleanup:)` with a required synchronous,
throwing cleanup callback. The actor validates identity and the completed journal
before invoking that callback, then removes the journal after cleanup succeeds.
Use its validated UUID for exact-user cleanup. The callback must tolerate a
missing directory on retry; failure keeps the existing journal as the obligation.
Relaunch readback comes from `accountDeletionStatuses()`.
See the source-preparation report at
`docs/reports/evidence/native-deletion-command-20261005/README.md` for dependency
order and explicit unrun checks. The native presentation/receipt cleanup adapter
is a later owned dependency.
