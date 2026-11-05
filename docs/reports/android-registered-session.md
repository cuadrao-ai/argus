# Android registered-session local acceptance

September 28, 2026. Implementation is locally verified; GitHub publication,
hosted CI and PR review remain pending publication. The founder has explicitly
authorized the branch push and PR creation.
This is not a merge/deployment or production-readiness claim.

## Delivered behavior

An explicitly configured local debug build adds optional registered sign-in
under Profile & settings. It calls existing Argus login and bearer `/me`, uses
Supabase Kotlin SDK 3.2.6 for refresh and actual local-session revocation, and
stores credentials with device-bound Android Keystore AES-GCM. Profiles remain
in memory. A failed verification hides private content while preserving retry;
a failed logout blocks replacement until revocation or authoritative rejection.
Guest sessions remain preserved without conversion. Browser recovery opens the
existing forgot-password route; native sign-in follows browser recovery.

Profile language drives English/es-419 resources. Composer drafts are scoped to
the controller's ownership epoch, hidden while identity is unverified, and
discarded at account retirement. Local-auth drafts are memory-only; the
default-off sample retains its prior saved-draft behavior. All financial
features remain samples. Release builds always disable authentication.

## Source and integration

- Branch: `codex/android-auth-continuation`.
- Spec-first commit: `f70cc747`.
- Implementation and screenshot source: `1e634a7795668c125378ec4f044a0762851f4482`.
- Original and freshly fetched integration: `19550f28e344c1004dd3ea366625c25fae4b3355`.
- No intervening integration changes, no reconciliation merge or semantic
  overlap. The current tree is the would-be merged tree; modularity passes.
- No server, API/data contract, iOS, web, analytics or financial implementation
  changes. Existing browser recovery code was run unchanged locally.

## Evidence

The [machine-readable record](evidence/android-registered-session/verification.json)
and sanitized [device logs](evidence/android-registered-session/device-core.txt)
contain local evidence. No credentials or tokens are committed.

| Check | Result |
| --- | --- |
| Opt-in debug build, JVM tests and lint | Pass; 33 JVM tests |
| Default-off debug and unsigned release builds | Pass; original 9 foundation device tests pass |
| Release configuration inspection | Disabled; all endpoints/keys empty; no debug cleartext configuration |
| Real local session lifecycle on emulator | Pass; encrypted storage, expiry refresh/rotation, profile hydration, logout, old-bearer rejection |
| Separate instrumentation processes | Pass; saved session restored after force-stop, then revoked |
| Real two-account UI | Pass; sign-in, switch, second profile, sign-out, draft isolation, browser intent |
| Synthetic UI regressions | 10 pass at compact and large phone sizes with 130% text |
| Local latest-fix review | Clean after fixing nullable provider fields, rejected-refresh logout and draft ownership |

Screenshots use synthetic profiles only. The compact 360×640dp view scrolls
vertically; the 411×891dp view shows all profile actions. Both use 130% text.

| State | Compact | Large |
| --- | --- | --- |
| English sign-in | [Image](evidence/android-registered-session/1080x1920/session-en-signed-out.png) | [Image](evidence/android-registered-session/1440x3120/session-en-signed-out.png) |
| Spanish verified profile | [Image](evidence/android-registered-session/1080x1920/session-es-verified.png) | [Image](evidence/android-registered-session/1440x3120/session-es-verified.png) |
| Retryable sign-out failure | [Image](evidence/android-registered-session/1080x1920/session-en-revocation-failed.png) | [Image](evidence/android-registered-session/1440x3120/session-en-revocation-failed.png) |

## Local setup and limits

Dedicated `Argus_Auth_611c` API36 ARM64 emulator on port 5584. These are emulator
results, not physical-device tests. Disposable Supabase project
`android-auth-611c` uses current migrations, generated local credentials,
synthetic accounts and CAPTCHA-disabled local auth. Ports: API59400,
gateway59401, DB59402, mail59403/59404; unchanged recovery web127.0.0.1:3000.
No other lane's service or adb daemon was stopped.

The native browser ACTION_VIEW target was asserted, and the unchanged browser
forgot-password form rendered. A complete password-reset journey was not run.
No production identity, CAPTCHA, App Links, signing, Play distribution,
financial API or guest conversion is accepted by this evidence. No model or
market-provider calls were needed.

## Remaining delivery gate

Publication was initially blocked because automatic approval review interpreted
“no hosted changes” as including GitHub publication. The founder subsequently
explicitly authorized pushing this branch and opening its PR in the delivery
lead chat. Hosted CI and the normal PR review loop remain required. No merge,
deployment or hosted configuration change is authorized.

The acceptance-artifact commit `19dc55a589f9c71aebb73bbdbc1b2cea3d2c71fd`
was revalidated with build/lint/JVM tests, real expiry-refresh-revocation,
account switching and separate-process restore. Its Android source tree
`ccb5ec18ae954175336cc83da46bb5086c037ed4` is identical to the screenshot
source commit; screenshots remain valid after documentation-only updates.
