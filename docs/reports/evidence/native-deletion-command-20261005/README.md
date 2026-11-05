# Native deletion command: source preparation

Status: command-core QA passed at `cc58b16f7f8ee4f520ffa4658f1396ba7a0cc4d7`.
The [published independent bundle](../native-deletion-core-20261005/independent-review/README.md)
owns the 168-test package run (164 passed, 4 existing opt-in skips), focused 19
passes, one real local SDK/API/Auth/Postgres case and generic app build. These
runs are separate. Analytics was synthetic; no provider, hosted, physical-phone
or final app-adapter journey was verified. Prerequisite landing and root review
remain required; this is not a release-ready claim.

The sections below record earlier source preparation and merge evidence, before
that independent QA. At source preparation, no Swift package, app build,
simulator, device, provider, hosted, database or service checks had run.

## Dependency and ownership

The immutable source base is `07f768f28be6f900b1a3d2e7b242bcdbad25d93a`, the native
Apple-name candidate. Dependency order is PR #864 (Apple session, including
`a24a` and integration `7d037`) → native Apple name → this command core → app
entry/confirmation/cleanup adapter. Root owns merge sequencing and Mac scheduling.
This candidate is not READY and must not be published as ready before its
prerequisites land and the affected checks run.

The existing SessionController and CredentialVault own the command, account
identity, epoch, proof and journal. A second deletion controller or credential
store was rejected because it would duplicate identity ownership. One token-free
vault envelope retains per-user commands, accepted acknowledgements and confirmed
local-cleanup obligations. The current SDK session remains the only proof owner.
The journal contains no JWT, refresh token or Apple code.

## Behavior

- Send one `POST /api/v1/account/delete` with `confirm: true` and, if supplied, one
  fresh ASCII Apple authorization code. Do not refresh, automatically retry,
  capture first, or sign in again to submit deletion.
- Journal uncertainty before transport. An interrupted command, lost response,
  malformed success or `503 account_deletion_incomplete` quarantines ordinary
  protected requests while keeping existing proof. Relaunch returns this state
  before any SDK refresh, profile fetch or Apple validation.
- Explicit same-command recovery uses only still-valid stored proof. Respect
  Retry-After. Expired/missing/refused proof offers support recovery, without an
  ordinary refresh. A refusal during earlier uncertainty keeps that uncertainty
  and bounded recovery metadata.
- Validate HTTP/body agreement. Only 200 `done` with an empty `pending` list proves
  completion. A 202 `in_progress` retires SDK proof and keeps a token-free per-user
  pending acknowledgement. It permits a later different account to sign in.
- Persist a confirmed exact-user cleanup obligation before retiring proof at 200.
  The initiating epoch is checked before issuing the receipt. Interruption of
  local credential removal can recover that receipt after relaunch/local removal,
  without another deletion POST. `accountDeletionStatuses()` derives readback from
  the same journal. A live SDK account suppresses confirmed-cleanup receipt
  delivery. The app acknowledges a receipt only after exact-user cleanup succeeds.

Minimal exhaustive adapter cases were required in ProfileAuthModel,
ConnectedCuadraoRoot and ProfileAccountSection. They use distinct uncertain and
pending states plus minimal EN/ES status strings. They do not add a deletion entry,
consequences, Apple UI, support action or receipt filesystem operation. Pending
copy makes no duration or automatic-operator promise. The recovered app UI owned
by Counsel must reconcile these small case additions through the root queue;
this source base still contains the earlier integration root.

## Verification prepared and performed

Synthetic test source covers validated completion, accepted proof retirement,
response loss and relaunch, protected-dispatch quarantine, request/body counts,
no refresh or capture, no Apple-code replay, Retry-After, fresh-authorization and
no-admission refusal classes, recovery refusal truth, malformed done, journal
write failure, interrupted local cleanup, account B after A acknowledgement,
stale snapshot/duplicate denial and expired proof.

`git diff --check` and Python modularity-budget checks pass on this source tree.
They do not verify Swift compilation or behavior. At initial preparation, Swift/package/app and real-device/provider/hosted evidence
were unrun. The published QA update above supersedes only its executed scope.
An independent read-only source review found cleanup recovery, new-account entry
after 202, recovery refusal truth and an adoption race in the interruption
handlers. Those gaps were fixed. The final review of the moved mutation guards
and gated adoption test found no blocker. That verdict is source review only.

The settled command contract is captured in the captain's native deletion
mapping. Backend/API, server policy, migrations, obligation semantics, consent,
space policy, flags and configuration are unchanged by this candidate. No paid,
live, physical-phone, provider, database, service or hosted claim follows from it.

## Apple-name dependency reconciliation (before independent QA)

Normal merge `e660fe9990b4a77779ba503b5cc3e3a9517dea70` reconciles current Name
head `a6efe6e3360f1c4e58c97807b91547de527b0b04` into the published deletion
source `e1a4fb2d055b6a6d06c0f360058bfb5e3878c6b2`. The original immutable
Name base remains `07f768f28be6f900b1a3d2e7b242bcdbad25d93a`. No rebase,
reset or stash was used.

The dependency delta has two affected files. Commit
`060a03f883f08fccdb613ee65343a8296a4793d7` renames the Apple XCTest fixture
property to `seedName`, avoiding the inherited XCTest property. Commit
`a6efe6e3360f1c4e58c97807b91547de527b0b04` moves Apple-name removal after
saving durable pending revocation proof in SessionController.

Semantic overlap exists in the shared session actor's retirement path, even
though Git reported no conflict. Source audit confirms that ordinary retirement
keeps pending proof before name cleanup can fail. Deletion uncertainty still
blocks that ordinary path; accepted 202 and confirmed 200 use the deletion
journal's separate fenced local retirement. The merge does not change the
CredentialVault deletion journal, deletion response parser, deletion test source,
completion receipts, minimal app case handling or localized strings. Independent
read-only affected-merge review at `e660fe999` found no concrete blocker.

The production delta against the current Name head remains this bounded deletion
slice: typed request/outcome parsing, journaled session command, protected-request
quarantine, per-user pending acknowledgements and completion cleanup receipts,
plus exhaustive app case handling and two EN/ES status strings. The dependency
merge adds no server, migration, flag, configuration or presentation expansion.

Diff and Python modularity checks pass on the merged tree. This preserves only
source/static review evidence. There was no deletion execution evidence to
retain or invalidate: package and app compilation/tests were queued for the final candidate head,
including deletion tests and affected Apple-name/session cases. The independent
bundle above records their later results. Mac and database leases remain with the current verifier; no Swift, Mac,
Postgres, provider, hosted, activation or root environment work ran here. Root
still owns PR creation, landing order and all merge decisions.


## Landed dependency reconciliation and core PR

Current integration `a2c65549b3ffcb97ee0be24b971110be8c090b32` includes guarded Name PR #874 over session PR #864.
Normal merge `03e9954744240c2bfd5b21d03005a7faa7e30fe8` reconciles it into the evidenced worker; source preparation
started from Name `07f768f28be6f900b1a3d2e7b242bcdbad25d93a`, which inherited
integration `7d037b07d4b98b34c6c0ad3026811c7d2f28ae47`. The immediately preceding
published evidence head was `21bb4c65c70a472f90b6c92c56c1255e5b0d1017`.

The squash landings caused shared-file conflicts. The resolved native files keep
the accepted deletion tree, not a hand-combined new implementation. Integration's
entire iOS tree matches the dependency's exact Name `a6efe6e` tree. All 403 native
Git objects and SHA-256 fingerprints also match tested `cc58b16f7`; there is no
new native runtime, identity, grant/capture, profile, vault, migration or test
behavior to remeasure. Name and Apple backend runtime owners and Supabase
migrations have no dependency-to-integration delta. The unrelated incoming runtime
change is Household invite-code lookup; env/web-recovery/docs changes stay owned
by their landed integration work.

Integration's fixed `tests/test_apple_name_api.py` and
`tests/test_profile_apple_identity_postgres.py` are preserved byte-for-byte.
The landed Name report is preserved from integration. No rebase, reset, stash,
Mac, PostgreSQL, provider, hosted or activation action was performed.

Accepted evidence is retained by exact source identity: full package 164 passes
and 4 existing opt-in skips, focused 19 passes, one actual local SDK/API/Auth/PG
case and generic app build. These are separate runs at `cc58`, not fresh execution
at the reconciliation head. Synthetic RecordingAnalyticsDeletion is not provider
completion proof. Independent affected-merge source review at `03e995474` found
no blocker. Fresh combined-tree modularity, changed-document links, Python AST,
JSON metadata, shell syntax and scoped whitespace checks pass. Terminal CI and
root PR review remain pending at publication.

This PR adds the command core and minimal exhaustive state cases. Uncertain
response state quarantines ordinary protected dispatch; accepted 202 retires
proof but preserves drafts and a per-user acknowledgement; confirmed 200 alone
issues a cleanup receipt. No one-time code is persisted/replayed or ordinary
refresh used for deletion. The next owned app adapter must wire entry,
confirmation, fresh Apple authorization, support and race-safe exact-user receipt
filesystem cleanup. Actual provider, hosted and physical-phone gates remain open.
