# iPhone registered-session acceptance

Local synthetic acceptance for [PR #738](https://github.com/lagarcess/argus/pull/738). This is an acceptance receipt, not the
terminal review/readiness audit. No hosted configuration, backend/web source,
financial records, signing account, provider turns, merge or deployment changed.

## Proven behavior

- Existing Argus login -> official Swift Auth SDK -> canonical `/me` identity ->
  device Keychain restore -> local-session revocation. Old access returned 401;
  old refresh returned 400. Two synthetic accounts remained isolated.
- Eight concurrent profile reads after the local 60-second JWT entered the SDK's
  expiry margin caused exactly one refresh and persisted rotated credentials.
- Invalid login was rejected. Confirmation-required signup did not invent a
  session, including an actual native signup showing Check your email.
- Native sign-in, process relaunch, sign-out and signed-out relaunch passed on
  iPhone17e (390×844pt) and iPhone18 Pro Max (440×956pt), iOS27 / Xcode27.
- CAPTCHA used the real WK widget with Cloudflare's public test sitekeys:
  success, failure and cancellation. The hold mode only pauses the local test
  page so cancellation can be exercised; native code has no token bypass.
- English and es-419 entry/signup/keyboard/appearance layouts passed on both
  sizes, including accessibilityXXXL dark text, reachable 44pt authored controls,
  descriptions and traits. Scrolling keeps all actions reachable.
- Existing web recovery passed in one private browser context: request email,
  follow local link, exchange PKCE code, reset, require fresh sign-in, reject
  old refresh and accept new password with matching `/me`.

See [session test receipts](session-tests.txt),
[simulator summaries](simulator-results.json), and
[recovery report](recovery/README.md). Screenshots are committed beside this file;
`compact-` and `large-` identify device sizes. All shown identities are synthetic.

## Corrections made during acceptance

The unsigned foundation app could not access simulator Keychain (securityd
-34018). Simulator-only ad-hoc signing now supplies a local application identity,
with no team or account. Actual relaunch proof passed afterward.

The accessibility audit found the authored Forgot password control's actual hit
area too small; sizing its label and policy-link labels fixed it. Manual review
also found faint default placeholders, now using the shared secondary text token.
The contrast audit reports the system glass Close button despite captured
black/white readable text; only that exact element's contrast finding is excluded.
Its semantics and action remain tested, and authored auth controls are audited.
The [actual flagged element](system-close-contrast-diagnostic.png) is retained.

Session tests reproduced late-response resurrection after an already-cleared
sign-out, failed-journal sign-out still appearing authenticated, and refused
refresh retaining usable auth. Account epochs, pending state and durable journal
ordering now cover these reachable cases. The final deterministic receipt names
all cases; SDK storage/transport injection supplies failure conditions.

## Scope and evidence limits

Financial screens remain local display samples, including after authentication.
No native guest entry/conversion, generic resend, recovery callbacks, financial
accounts, providers, sharing or voice is implemented. Guest credentials, if
unexpectedly present, are preserved and native replacement is refused.

This proves local integration with unchanged Argus/Supabase, not hosted or
physical-device readiness. Production CAPTCHA hosting, signing and bundle identity
remain unresolved. Browser proof uses the existing web development CAPTCHA token;
its old 60-second access JWT may have expired, so its 401 alone does not establish
revocation. The old refresh rejection and web global-sign-out result provide the
additional proof. Native CAPTCHA proof uses the public widget test mode only.

Pending sign-out, storage failures, stale requests and refused refresh are
verified with the actual SDK at the session boundary and inspected in the typed
SwiftUI binding. No simulator OS-Keychain corruption or hosted failure was
injected. Physical-device VoiceOver and native recovery return are not claimed.

## Source and repetition

The bounded spec was committed first at 661318138d53882b5280685a39a0e6b9a1c46385,
from freshly fetched integration 19550f28e344c1004dd3ea366625c25fae4b3355.
Design reference #727: f0a64ffb9d70ce5b82491cf8e1803bb8a6ec7431.
Auth evidence #726: d03f3c265604f7c73f65886740d32ddfe190e85d.
Initial implementation: af6e62b1b715cb5420aa9883b038b136a7c585c1.

The earlier live package proof is retained: subsequent package changes only fix
failed-storage/rejected-refresh/stale-response paths and pass deterministic
regressions. The final native registered journey revalidates successful lifecycle
behavior. Earlier signed-in screenshots retain the same rendered view; final
bilingual captures revalidate the later touch-target/placeholder changes.
Recovery's web source hashes remain byte-identical. Formatting the proof helper
after capture did not change web source or recovery behavior.

Run commands are in AUTH_SETUP (removed; see tag `archive/ios-personal-2026-10-30`). Raw `.xcresult`,
private fixtures, session material and browser logs remain ignored. Only named
screenshots, safe test summaries and source/hash receipts are promoted here.
Final source hashes, reconciliation and cleanup are recorded with the completed
acceptance; the terminal PR audit follows the final Codex review.

Final implementation source: `d024639b92997dea110ae98468ece0831d2fa9d8`.
[source-manifest.json](source-manifest.json) pins every tracked iOS source/config/test/helper file. Later evidence-only commits do not change these bytes.
