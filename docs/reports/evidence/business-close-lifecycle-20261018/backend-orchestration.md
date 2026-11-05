# Backend deletion and purge checkpoint, October 18, 2026

This backend checkpoint completes Required continuation steps 1 through 4 from
`transfer-successor.md` in draft PR #1222. It builds on
`3bb6d448badf19dac8e5971f011cd0dbba3bec9a`. The recorded and refreshed integration
base is `651870a54be4e5506dbb38f3902fef1a97eef8df`. Integration did not advance,
so no reconciliation merge was needed. No published branch was rebased.

This is local synthetic backend proof. The whole lane remains WIP. Global
account deletion stays off, the lifecycle readiness dependency still refuses
requests, and the new lifecycle and transfer routers remain unmounted. No
hosted migration, merge, deploy, real Auth/Storage/provider call or email ran.

## Saved behavior

The existing claimed account-deletion command captures provider revocation
credentials before any custody writer can clear source secrets. It prepares
hash-and-size-verified original and rebuilt copies, then detaches every Business
whose stable custodian is leaving. This precedes the personal source transaction
and old-prefix erasure. A failed copy preserves the original graph and bytes.
A retry reuses the saved reservation and copy plan. Claims renew around copy
I/O and every guarded graph operation.

Closed Businesses keep their original `closed_at`. The departing closed owner
becomes NULL, so nobody can reopen an ownerless Business. Active transferred
Businesses retain the new current owner. Transfer still leaves the former owner
with Editar until their account-deletion command removes their access.

Departing members and transfer targets need no custody copy. Their personal
transfer outbox rows and access are removed, pending transfers are cancelled,
and saved actions use a random scoped historical actor. Their actions never
become the new owner's actions. The alias has no Auth account or grant. The
existing custody identity guard and transfer-outbox Auth guard stay composed.

`retained_dependencies` must be empty before Storage or Auth erasure. Successful
Auth API return alone cannot settle deletion. Both the adapter and database
must confirm Auth absence. The command then calls `complete_identity_cleanup`
for every custody move and clears member identity maps, before global settlement
removes the person's ID, hashes, claims and revocation payloads.

The existing operator deletion sweep now also handles closed Businesses at
`closed_at + 30 days`. It records an exact object plan before deleting the scoped
Business graph. It removes canonical rows, revision graphs, conversations,
checkpoints, email/WhatsApp transport and scoped retry budgets. Original,
rebuilt and reserved orphan-copy paths are removed with readback, then the
Business-only placeholder is removed with verified Auth absence. The private
retry plan survives a graph or Storage failure. A completed receipt retains no
object paths or real person ID. Shared bytes referenced by another live scope
stay in that scope. Two sweep passes cannot run one claimed plan together.

## Local verification

The final combined run passed **318 tests**, with **3 skips** and no failures.
All new account-deletion and purge cases passed. The skipped existing tests are
`test_account_deletion_api_postgres.py:273` and
`test_account_deletion_third_parties_postgres.py:449,558`; they require a local
Supabase Storage service. They are not claimed as real Storage proof.

The run includes all `tests/test_account_deletion*.py` files and these files.

- `test_business_account_deletion_postgres.py` and `test_business_purge_postgres.py`.
- `test_business_custody_graph_postgres.py` and `test_business_custody_objects.py`.
- `test_business_lifecycle_postgres.py` and `test_business_lifecycle_routes.py`.
- `test_business_transfer_postgres.py` and `test_business_transfer_routes.py`.
- `test_business_transfer_mail_postgres.py` and `test_business_transfer_mail.py`.
- `test_business_access_postgres.py`.
- `test_resume_account_deletions.py` and `test_force_account_deletion_step.py`.

The saved-state checks cover closed and transferred custody, multiple closed
Businesses sharing one old prefix, source/revision links and hashes, failed
copy retry, delayed Auth absence, departing noncustodian members and targets,
anonymous attribution, removed mail transport, day-30 boundary, ownerless purge,
failed graph and Storage retry, concurrent sweeps and cross-Business isolation.
The canonical FK census was refreshed from the actual synthetic catalog. The
Auth-trigger test retains the original signup checks and verifies the added
read-only SECURITY DEFINER delete guard has no private-schema WHEN expression.

Ruff, whitespace, branch ownership and modularity budget checks passed. No
model-facing prompt or schema description changed. Model the Domain kept live
identity and anonymous history separate. Make Operations Idempotent led to the
persisted purge plan and readback before settlement.

The owned `business_deletion_orchestration_testdb` was cloned from the preserved
`business_close_testdb`. Only that new database received checked-in forward
migrations 20261019000005 through 20261019000008. The root baseline `postgres` database and the
source fixture were not changed. Python was the shared read-only 3.10 runtime.
`load_project_dotenv` was disabled in the test process and provider credentials
were blanked. External Auth, Storage, SMTP and provider effects used fake
adapters. The owned database is dropped after verification. The temporary test
checklist is removed. Source worktree, configuration and committed evidence stay.

## Handoff to the final lifecycle writer

The final writer still owns Required continuation step 5. Wire the account
warning to actual current-owner Business discovery and working close and
request-transfer controls. Use `current_owner_id` for authority and preserve
custody IDs. Each Business needs its own controls and existing export entry.
Use the approved copy without edits.

`PostgresBusinessLifecycle.closed_spaces(owner_id)` already returns only the
current owner's closed Businesses inside the reopen window. An ownerless
Business is absent and `_owned_space` refuses reopening. Wire the list and
reopen control to these existing methods. Add the approved member-close email
queue to the actual committed close path through the existing canonical layout
and sender; no mail or environment mutation is authorized by this checkpoint.

Keep the readiness denial and global deletion off through that work. Required
continuation step 6 remains with root. All three receipt cases must pass, then
independent final Eval and Rafael's permission retest must run on the reconciled
final head. Only root can consider integration or staging under separate grants.
New migrations 20261019000007 and 20261019000008 can reach staging only through the merged PR.
