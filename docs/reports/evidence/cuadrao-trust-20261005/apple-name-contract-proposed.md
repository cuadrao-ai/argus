# Apple first-authorization name: bounded next-slice contract

Read-only proposal, October 5, 2026. No implementation, test execution, Mac build, PostgreSQL run, provider call, hosted change, or modification of another writer's checkout occurred.

## Baseline and authority

Inspected `/private/tmp/cuadrao-trust-20261005`: working HEAD `61599222f9e251f93a9e54865a41e149e92765a7`; remote-tracking integration `7018e0edebbc370b999005a857230bf3c3a1ad8b`. These differ. Integration Apple identity code was read explicitly with `git show origin/codex/private-alpha-next:...`; this is not a claim that the checkout includes all integration work. No fetch or branch mutation occurred.

Read AGENTS, product/document-authority/MVEE, architecture, profile API/data contracts, design guidance and relevant source. The earlier `/private/tmp/cuadrao-identity-remaining-contract-20261005.md` is a proposal, not independent founder approval. Current task authorizes first-authorization name persistence without overwriting later user edits. Root confirms no additional founder name decision is recorded.

Settled repository semantics:

- `profiles.display_name` is account identity presentation. `preferred_name` is a separately chosen form of address and must not be inferred from Apple. `docs/DATA_MODEL.md:243` and `docs/API_CONTRACT.md:1041` own this distinction.
- `docs/reports/evidence/cuadrao-trust-20261005/decisions.tsv` records the founder's Apple-session-only validation decision. Unknown mixed-provider grant provenance requires explicit reauthentication. This slice must preserve the session branch's implementation of that decision.
- Native providers remain default off, Release remains forced off. No activation or identity merge is authorized.
- Profile PATCH partial-column writes belong to #853. Session journal, successful-grant provenance, Apple validation and awaited capture belong to the active session writer. Land both before this slice edits those owners.

## Traced reachable path

1. `ios/ArgusFoundation/Auth/NativeProviderSignIn.swift`, `ConnectedProviderButtons.completeApple(_:)`: request asks for `.fullName` and `.email`; completion reads ID token and authorization code but never reads `apple.fullName`. This is the loss point. It is reachable only when the existing Apple provider gates expose the connected button.
2. `ios/ArgusFoundation/Auth/ProfileAuthModel.swift`, `signIn(with:appleAuthorizationCode:)`: adopts the session and currently starts best-effort capture. The session branch replaces that behavior; do not rebuild its logic from the older checkout.
3. `ios/Packages/ArgusSession/Sources/ArgusSession/SessionController.swift`, `signIn(with:)`: isolated Supabase `signInWithIdToken` exchange, then journaled `adopt(_:)`, then `/me`. The actor and its vault own account epoch and session identity.
4. `ios/Packages/ArgusSession/Sources/ArgusSession/CredentialStorage.swift`: `PendingCredentials`, `CredentialVault.savePending`, SDK storage and epoch validation. `.pending` currently means adoption/revocation recovery; it cannot casually become a name-retry marker because restore treats it as pending sign-out.
5. `src/argus/api/dependencies.py` invokes `SupabaseGateway.get_or_create_profile_for_auth_user`. `src/argus/domain/supabase_gateway.py:1999` creates a missing profile from `user_metadata.display_name` only. It does not read `full_name`, and existing profiles return without name reseeding. Creation uses insert-on-conflict-ignore, then rereads.
6. `src/argus/api/routers/profile.py:314`, `patch_me`, owns intentional profile edits. #853 changes its full-row persistence to explicit patched columns; otherwise a concurrent unrelated edit can restore an obsolete name.
7. Integration already owns `src/argus/domain/apple_sign_in/identity.py`: `linked_apple_identity(connection: Connection, user_id: str, *, lock: bool = False) -> LinkedAppleIdentity | None`. Reuse this reader; do not add email/provider-metadata inference.

No inspected path persists the Apple full name into Supabase Auth metadata. Writing `full_name` there would not feed current profile creation. Writing `display_name` after `/me` would also be too late for an already-created profile. Repeated metadata reconciliation would introduce a second name owner.

## Smallest safe server contract

Use a distinct idempotent profile command, not token capture and not ordinary PATCH:

```text
POST /api/v1/me/apple-name
{ "display_name": <nonblank Unicode string> }
200: canonical UserResponse
```

Return the existing canonical envelope whether the name was initialized or preserved. The client needs a successful canonical result, not a second profile representation or a distinction that requires a receipt table. No request user ID, email, Apple subject, preferred name or auth metadata.

Registered-owner authorization derives from existing `current_user` and account capability. Resolve current linked Apple identity with the canonical reader, fail closed on absence/ambiguity. This is user-supplied presentation text, not verified legal identity. No provider exchange or ID-token parsing is needed for this command. Existing admission/deletion guards still apply.

Normalize trim at the boundary, retain Unicode and interior spelling. Current display-name schema has no established length bound; the implementation should introduce a local request maximum (recommend 200 characters) with 422 rejection rather than truncation. Do not reuse the 40-character preferred-name rule. The iOS formatter uses `PersonNameComponentsFormatter` rather than concatenating given/family components; empty formatted input means no seed request.

Proposed narrow persistence entry point, in a focused profile module rather than growing Apple token storage:

```python
def initialize_apple_display_name(
    *, user_id: str, display_name: str
) -> User: ...
```

One short database transaction checks linked identity and conditionally updates the canonical profile. Return the canonical profile after conditional update/no-op. Use a DB row lock or conditional UPDATE and reread in the same transaction. Do not hold a DB transaction across network/provider calls.

Add one internal monotonic `profiles.name_initialization_closed` boolean, not another name value:

- New profile inserted with any explicit display/preferred name starts closed; new unnamed profile starts open.
- Successful initialization writes display_name and closes eligibility atomically.
- Explicit UPDATE OF display_name or preferred_name closes eligibility even for NULL-to-NULL, blank-normalized clears, or setting the same value.
- Initializer requires eligibility open AND both names absent. It never writes preferred_name.
- Unrelated PATCH columns leave eligibility alone. #853 is therefore a hard prerequisite.
- A database trigger enforces closure for all writers, including direct authenticated preferred-name updates allowed by `20260809140000_add_preferred_name.sql` and retained by `20261005090000_explicit_client_grants.sql`.
- A closure marker cannot be reopened by an ordinary write; clients get no new marker column privilege or API field. A BEFORE INSERT trigger must override attempts to insert a false marker alongside a name; BEFORE UPDATE logic retains a previously true value.

This marker is required implementation machinery for the authorized explicit-clear guarantee. Testing only `display_name IS NULL` would forget that a user deliberately cleared it. Metadata flags or frontend read-then-PATCH cannot establish the guarantee.

Historical rows: no persisted fact distinguishes a never-named old profile from one explicitly cleared in the past. Safest migration marks all existing profiles closed. This follows the stronger preserve-edits constraint; automatic backfill of old blank rows cannot also promise that constraint. Existing users retain ordinary manual editing. If scope expressly requires auto-seeding previously existing blank profiles, the captain must choose between historical-clear preservation and opportunistic backfill; code cannot infer both. Newly created post-migration profiles remain eligible.

## Native contract and durability

Extend the landed session owner, not a new name manager or UI cache. Proposed caller shape (adapt names to the landed session branch):

```swift
// At the actual Apple callback, before discarding ASAuthorizationAppleIDCredential.
let initialName = apple.fullName.map { PersonNameComponentsFormatter().string(from: $0) }
let result = await auth.signIn(with: credential,
                              appleAuthorizationCode: code,
                              initialAppleDisplayName: initialName)
```

The optional input belongs to Apple sign-in orchestration, not the generic ID-token payload sent to Supabase. The UI forwards it; SessionController owns persistence/retry and canonical snapshot adoption. Add a bounded retry entry point such as `retryAppleNameInitialization(expectedIdentity:) -> SessionSnapshot`; it loads its own journaled intent, not a caller-supplied replacement name.

Persist the unsatisfied initialization intent as part of the existing session/adoption envelope. The payload contains only account-bound pending display-name input and the minimum existing account/epoch binding. It is an outstanding command, not a second authoritative profile. The existing Keychain protection and cleanup owner apply. The new intent must survive SDK refresh writes; test that explicitly against the session branch's envelope preservation code. Do not put names in UserDefaults, analytics, logs, or a parallel profile store.

Carry intent through adoption before any profile/name request can suspend. When an authenticated session is durable, retain the intent in that session envelope until a canonical 200 result is durably acknowledged. `restore` resumes it through the same authenticated transport after the session branch's Apple-validation gate passes. Do not store it only in `.pending`: restore currently revokes that journal. A stale epoch, sign-out, deletion or different user prevents dispatch and clears it through existing account retirement. Never replay a pending name onto the next account.

Name saving must remain independent of one-time code capture: save-name retry never resubmits the authorization code or invokes Supabase sign-in. A capture failure does not erase pending name intent. An unavailable name endpoint leaves a recoverable name-save state and does not pretend sign-in failed; the canonical account remains signed in. Return to the existing invitation flow only through its existing owner.

Crash-boundary caution: the old proposal's memory-only retry loses first-authorization names on relaunch and is insufficient for an advertised crash-safe guarantee. Extending the existing durable envelope resolves crashes after grant/adoption journaling. A crash between receiving Apple's callback and obtaining/journaling the Supabase grant is earlier: to promise recovery there too, an account-unbound pre-grant intent must be persisted by the SAME vault owner before the first await, bound to the Apple credential subject and accepted only after server identity verification. It must contain no ID token/code and never seed another account. This is feasible but adds a pre-grant state and requires bounded cleanup/retention. Do not claim this interval covered by post-grant journaling.

Recommended narrow finish line: durable retry from successfully journaled Supabase grant, explicit manual recovery if Apple returned no name or the grant never became durable. If 'first-authorization persistence' is intended to include every callback-to-grant crash, explicitly include that pre-grant state in the slice rather than silently weakening the guarantee. That precise durability boundary is the one remaining product/scope choice; storage implementation and atomic edit priority are engineering decisions.

## Concurrent operations and verification plan

Do not run these checks until the captain assigns the implementation and serial Mac/PG slot.

Backend behavioral matrix (parameterized with realistic reusable profile fixtures):

- New eligible profile + formatted name saves only display_name; /me after fresh request/relaunch reads it.
- Repeat seed and response-lost retry converge to the same row. Different repeated seed cannot replace the first.
- Existing display name, existing preferred name, intentional null clear, same-value update and direct preferred-name column update preserve user intent.
- Two connections race seed versus explicit name edit/clear, in both orderings; the explicit edit wins. Race seed versus unrelated locale/currency PATCH; no name rollback and no lost preference.
- Marker cannot be reset by service patch model, authenticated column write, guest or another account. API rejects guest/non-owner/missing or ambiguous Apple identity.
- Existing-row migration closes unknown history; new unnamed insertion remains open; metadata-created names start closed.
- Unicode/multipart names retained, blank absent, oversized request rejected; preferred name stays untouched.
- No provider invocation for any name route, including retry; existing token-capture behavior unchanged.

Native fault matrix using the existing fake Supabase/API transport and injected checker:

- Actual callback extraction forwards fullName; nil/repeat authorization sends no name.
- Lost name response after server commit, transient failure before commit, failure clearing acknowledged intent, process reconstruction, refresh before retry, and cancellation.
- Inject a stop at each journal/adoption transition; after restart either same-account pending command is retained safely or existing session recovery is explicit. Never describe successful credential adoption as name persistence evidence.
- User edits name while pending seed retries: server returns canonical chosen value and journal drains without overwrite.
- Account A pending completion after sign-out/sign-in B cannot update B or render A's profile; Apple validation pending prevents name dispatch just like every protected request.
- Name/capture failures remain separately classified; name retry performs zero code exchanges and zero new provider grants.
- Manual-name recovery and return-to-invitation use reachable connected UI in en/es-419; gallery-only ReleaseSocialSignInView is not acceptance evidence.

After implementation: focused backend tests + real isolated PG concurrency/privilege tests, Session package tests, affected app-model/native UI checks on the serial Mac slot, generated OpenAPI parity, modularity on reconciled integration tree, durable exact-head synthetic evidence. Physical Apple first/repeat authorization and actual iPhone relaunch remain a separately authorized provider/device gate.

## Scope, sequencing and stop conditions

One independently reviewable PR after #853 and the session branch land. Allowed owners: focused profile initialization module/route/schema, one additive migration and trigger, existing session/adoption envelope and Apple callback/model, relevant tests and API/data/native auth docs. Share no active writer files. Reconcile against actual landing SHAs before implementation.

No token-capture redesign, deletion redesign, Apple/Google activation, email/relay matching, identity linking, broad auth-metadata synchronization, web auth work, analytics changes, provider calls, hosted migration or production write. Pause if a required safety guarantee would need one of these.

Work record: grounding and contract complete; implementation/Mac/PG skipped by assignment. Used poteto-mode/how/architect as scoped read-only grounding rather than starting an implementation arena. Model the Domain shaped the internal eligibility fact and command intent; Make Operations Idempotent shaped conditional initialization and durable replay. No child agents, processes, new worktrees, or other resources were created. This report is the sole written artifact.
