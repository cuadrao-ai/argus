# Combined Apple name and deletion admission proof

October 5, 2026. PR #862 landed as
`7c2522fb7d08f183bb1b07cd9b4aabe829089dc0`, following `fc4057c87`.
The published #869 branch normally merged current integration at
`5412f94cdcb8c7abb278d8f99ee40879f44c708f`; it was not rebased.
The original integration base remains
`2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`.
The final pre-publication fetch still resolved to `7c2522fb7`.

## Semantic overlap

Deletion admission now locks `auth.users FOR UPDATE` through its canonical
`lock_apple_state` owner before resolving the identity, credential and run.
The unchanged name initializer holds the same parent `FOR SHARE` before its
identity, deletion-state and profile reads. These locks conflict. READ COMMITTED
and separate post-lock statements let a waiting name command see the newly
committed deletion run. No second admission oracle was introduced.

The normal merge brought the already-reviewed deletion service and credential
changes plus API/data/OpenAPI sections. Name request, command, route, exposure
gate, profile writer and name migration sources were unchanged. Generated
OpenAPI was regenerated and produced no diff after the automatic merge; the
runtime/artifact parity tests passed. The overlapping privacy/deletion claims
were read together. The name API contract now records the verified parent-lock
behavior instead of a pending #862 dependency.

## Real transaction and API proof

Four new cases call the actual `AccountDeletionService._claim`, its real
household repository connection and canonical parent-lock helper, alongside the
actual name initializer. Both initial operations run real PostgreSQL transactions.
A test transaction envelope pauses only after the first actual operation has
written, before its outer commit. An independent autocommit observer proves that
the second connection is blocked using `pg_blocking_pids` before release.

- Deletion first, commit. The waiting name request is denied. Its full profile
  tuple, including timestamp and eligibility, is unchanged. Subsequent name
  retries are also denied.
- Name first, commit. The seed succeeds before the waiting deletion admission
  can commit. Once admitted, later name retries are denied and preserve the row.
- Deletion first, interrupted. The real admission transaction rolls back with
  no run. The waiting name completes; retrying deletion then admits one run and
  blocks subsequent name writes.
- Name first, interrupted. The seed transaction rolls back without a name or
  eligibility mutation. Waiting deletion commits; retrying the name is denied.

Duplicate deletion claims report `in_progress` while the existing claim is live.
After release, retry acquires the same run ID; the database contains exactly one
run. These cases execute no provider request. The Apple service reads a real
synthetic sealed credential; its HTTP transport is fake and records zero calls.

The signed local Supabase Auth/API journey additionally admits deletion through
the same actual command. A later authenticated name POST returns 401 through the
existing session admission owner, never dispatches the name initializer, and
leaves the entire protected profile tuple unchanged. This is local real Auth
proof; it is not proof of Apple provider authorization or revocation.

## Counts and cleanup

The combined memory API/contract cohort passed **104**, zero failures/skips,
in **4.56s**. This retains all 72 name/capture/OpenAPI checks and adds 32 existing
deletion API checks.

The final configured local database/Auth cohort passed **77**, zero failures/
skips, in **9.30s**, with **27** existing pool-default deprecation warnings.
It covers the 32 name persistence/privilege races, signed Auth/API journey,
four new name/admission races, currency concurrency, 12 canonical identity cases,
and 27 existing Apple deletion-admission cases. The four new races separately
passed in 1.87s after fixture cleanup was corrected.

The first new race run had four passing bodies and four teardown errors because
the synthetic Apple credential has a RESTRICT Auth FK. The fixture now deletes
only its own credential before its own Auth user cleanup. The four exact
generated IDs from that failed run were cleaned; the subsequent runs completed
without teardown errors. No shared table reset, other worker fixture cleanup,
stack stop, hosted operation or native/Mac run occurred.

Ruff and whitespace pass. The budget on the combined integration result has
zero violations. Sanitized summaries and `reconciliation-862.json` retain the
counts. The final evidence changes do not alter runtime owners. Independent
delta review, exact-head CI and guarded merge remain the captain's work.

Native callback/journal/relaunch, real Apple authorization, the physical phone,
hosted migration/readback and feature activation remain open. The existing
Apple gate stays default off. No parent issue is closed by this server slice.
