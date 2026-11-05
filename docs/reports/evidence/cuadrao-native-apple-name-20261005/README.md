# Native Apple first-authorization name

## Scope and lineage

The native callback now formats Apple's `fullName` with `PersonNameComponentsFormatter` and synchronously journals the input through the existing `CredentialVault` before starting asynchronous sign-in. Names never enter Auth metadata or a second profile store. The API response remains the canonical profile.

Original dependency head is PR #864 commit `a24a6c60627460ddfd6042b3f42b342c5eff11f0`. Server name command is settled by PR #869. Original integration reference is `7d037b07d4b98b34c6c0ad3026811c7d2f28ae47`, merged normally into the isolated native branch. Intervening integration changes concern server money/deletion, environment membership and documentation. There is no native session-owner overlap. The name command consumes the landed server contract.

PR #864 landed as `5d46a73d4d97b0412dccff517eb43c73e4316977` and was normally merged into this branch as `9144553f8da6dc7c36f02e6f137cd2cb44fa1c6b`. Exact-head CI and the final review remain pending. Independent native verification has finished at the source head recorded below. Global providers remain off. Evidence publication performs no provider, hosted, paid, simulator or device action.

## Caller and ownership

```swift
let name = apple.fullName.map { PersonNameComponentsFormatter().string(from: $0) }
let authorization = try auth.prepareAppleName(displayName: name, subject: apple.user)
// The preceding call completes before the callback starts its Task.
let outcome = try await controller.signIn(with: credential,
    appleAuthorizationCode: code, appleNameAuthorization: authorization)
```

A vault-owned pregrant record contains only intent UUID, Apple subject, display name and creation time. It expires after 24 hours, is pruned on restore or the next callback, and requires a fresh successful Apple grant for the same subject after an interrupted exchange. Restore never replays a stored authorization code or ID token. No code/token is stored in the pregrant intent.

Actual grant adoption promotes the intent into `StoredSession` with durable user UUID and grant UUID, under `.apple` sign-in provenance. Existing `PendingCredentials` retains its revoke/adoption meaning. SDK refresh derives the pending command and grant method from that envelope. Before dispatch, the session owner requires the current account epoch, canonical `/me` user ID, canonical Apple subject and successful Apple credential validation. Different subjects discard the command without dispatch.

`POST /api/v1/me/apple-name` receives only `display_name`. A canonical successful envelope, including a server no-op for an existing name or explicit clear, acknowledges the exact bound intent. A lost response or outage retains the account-bound command for restore or `retryAppleNameInitialization(expectedIdentity:)`. Name failure remains separate from code capture and never replays its one-time code. Sign-out and refused adoption use the existing account retirement owner. An unavailable adoption before `/me` succeeds preserves the subject-only callback for a fresh grant; no signed-in claim is made for an incomplete adoption.

Two alternatives were considered. Replacing the entire vault with one large envelope gives atomic transition writes but rewrites mature revocation storage. Keeping a separate command journal throughout its life duplicates cross-record account binding. Pregrant record followed by the existing session envelope is the smallest design that covers the callback-to-grant interval and keeps authenticated facts in one owner. Keeping the pregrant copy until successful adoption handles a crash between promotion and cleanup.

## Verification status

Synthetic regression source covers callback durability before grant, Unicode/trim, name outage, lost response/relaunch, no code replay, explicit edit/clear no-op, different subjects, sign-out/stale identity, denied adoption, SDK refresh preservation, unknown grant refusal, expiry, late revalidation, uncertain Apple validation, callback storage failure and failed durable acknowledgement.

Independent QA passed at production source `a6efe6e3360f1c4e58c97807b91547de527b0b04`. The [published independent report](../apple-name-native-20261005/independent-review/README.md) records these separate runs:

- Full package: 150 passed, 4 opt-in skips, 0 failures.
- Focused name and existing sign-out regression: 16 passed.
- Independent changed-boundary cases: 3 passed.
- Signed current-source local Auth/API/PostgreSQL journey: 1 passed.
- Actual provider configuration: 22 passed (11 Debug, 11 Release).
- Actual ProfileAuthModel UI journey: 1 passed, four screenshots.

Both introduced failures remain in the bundle: the XCTest `name` property compile conflict, fixed by `060a03f883f08fccdb613ee65343a8296a4793d7`, and the existing deletion recovery regression caused by pregrant cleanup before pending-credential storage, fixed by `a6efe6e3360f1c4e58c97807b91547de527b0b04`. Baseline and failing outputs are historical evidence, not final acceptance counts. The independent harness's own initial compile failure is also preserved.

The 29 source-manifest entries plus original `files.json` are published under the independent report. `publication-manifest.json` records original and published hashes, log whitespace normalization and one report filename correction. Screenshots and diagnostic patches remain byte-for-byte copies. The evidence-only commit preserves every production/test source file from the tested head, so that source-scoped evidence remains applicable; it does not establish later reconciliation or terminal CI.

## Reconciliation and retained evidence

[Reconciliation fingerprints](reconciliation.json) verify all 401 tracked iOS files against the accepted `a6efe6e` source. None changed. The existing session actor, vault, callback, model, package tests, native configuration, shared money/currency actors and native UI sources remain identical. Profile/Apple identity/name command, schema, auth dependencies, Supabase gateway and the signed local name test also remain identical.

Seven textual conflicts arose because the dependency landed by squash. Five incoming native files match original dependency `a24a6c6` byte-for-byte, so their tested Name extensions were retained. The two server test conflicts take integration's final fixture/import and isolated local Auth environment repairs. Those repairs alter test setup, not the profile response or identity contract.

Other integration changes concern web password-recovery IP routing, release environment key ownership/default-off invite declarations, tests, documentation and an invite-secret explanatory comment. They do not change native authentication dispatch, name claim/initialization, durable session state, profile currency or server Apple identity resolution. No new migration or environment setting is introduced by this Name diff. No provider or hosted activation occurred.

All recorded native and signed-local name evidence is retained by this source comparison; none is invalidated. Tests were not rerun during reconciliation. The [merged-tree budget](modularity-reconciled.txt) passes. The Name diff's whitespace check passes outside byte-preserved diagnostic patches; their mandatory context-line spaces are checked with only blank-at-eol/blank-at-eof disabled. Existing whitespace in incoming integration evidence is preserved.

The independent publication review was reported clean by the captain. Physical Apple first/repeat authorization, physical-device acceptance and activation remain open. This PR does not close #800/#798 or assert READY; exact-head CI and final scoped review are still required.
