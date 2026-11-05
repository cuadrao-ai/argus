# Apple display-name server slice

October 5, 2026. Server implementation only, default off. This command lets the
native owner save the first Apple authorization's display name without replacing
a later account-name choice. It never supplies a greeting/preferred name.

Original fetched integration base was
`2b2d0d9e8ed311c11b7585fbd757fb37f915e12f`, after #853's partial profile writer.
Source commit is `fc40d576e`; current integration was fetched again as
`fc4057c8789d3e3504fcb0e980344d6bf51e66c0`. Its normal reconciliation merge is
`8d5cc0192758138069ef21b83b9b2c5696cb323a`.
The intervening #868 change touched the shared Apple identity test observer and
evidence only. Runtime Auth, profile, migration, environment and native owners
were unchanged. Both source commits have the same `src` tree
`6dc988f48edaa23cfb82759b03d4f598fbae1860`.

## Behavior and ownership

The existing profile is the only name store. The new internal boolean records
only whether initialization is permanently closed. Database triggers close it
for explicit name edits, including NULL-to-NULL clears and same-value writes.
They prevent reopening and named inserts claiming open eligibility. Historical
rows start closed because their prior clear/edit history cannot be established.
Unrelated partial preferences leave a new unnamed profile eligible.

The registered-owner command uses the canonical current linked-Apple reader,
Auth-parent and identity locks, and one profile-row transaction. It preserves
the existing `/me` response and account-capability owner. The existing Apple
capture flag hides it before body/auth processing. No provider call, Auth
metadata copy, client marker privilege or native code was added.

## Local proof

The initial three valid-fixture tests failed on the baseline because the
initializer module did not exist. The implementation passed those three tests.
Initial fixture errors from mismatched verified email, absent synthetic Auth
identity timestamps and an invalid deletion hash were repaired before proof.
An accidental combined run mixed durable mode with memory-only fixtures and
reported 11 failures, 65 passes and 30 setup errors. That setup is not a pass;
the final cohorts run separately in their required persistence modes.

The focused memory cohort passed 72 tests with zero failures/skips in 4.59s.
It covers new request validation and accurate errors, default-off denial before
body/auth, guest/no-session denials, the existing Apple capture API and generated
OpenAPI parity. After reconciliation it passed 72 again, zero failures/skips,
in 4.33s. The configured durable cohort
passed 34 tests with zero failures/skips in 3.59s before reconciliation. After
reconciliation, adding the current shared identity suite produced 46 passes,
zero failures/skips, in 5.74s.

The durable matrix includes 32 new Postgres cases, one new signed local
Auth/API/reconstructed-client journey, and the existing #853 currency concurrent
preference journey. Twelve race cases use an autocommit statistics observer and
`pg_blocking_pids` to prove an actual blocked writer before releasing the first
transaction. Both orderings preserve explicit display/preferred edits and NULL
clears. Unrelated locale/currency writes preserve the seed and their preference.
Four client marker read/write denials, two direct guest/stranger denials and a
direct authenticated NULL preferred-name clear have no unauthorized name effects.
Missing, malformed, ambiguous, banned, deleted and already-deleting accounts do
not write a name. Retry with a different seed preserves the first result.

The same migration was executed against historical/new synthetic rows in a
worker-owned random schema, rolled back afterward. Only the additive migration
was applied to the shared isolated stack. Fixtures clean only their own Auth
IDs, identity rows and synthetic deletion runs. No stack/container was stopped.
Ruff, whitespace and the combined modularity budget pass with zero violations.

## Remaining gates

At this initial checkpoint, concurrent deletion-admission serialization depended on #862 taking the
same Auth-parent lock. This slice is sequenced after #862 in the captain's merge
queue; current prior deletion admission is not claimed race-safe. Combined
admission proof had to be rerun after that landing and normal reconciliation.
The [subsequent combined proof](reconciliation-862.md) now closes that local
dependency. Native, provider, phone and hosted gates below remain open.

Native callback extraction, durable command journaling, refreshed/reconstructed
session replay, account retirement and user-visible recovery belong to the
following native slice after #864. No native first-authorization, simulator or
physical-device acceptance is established here. Real Apple authorization and
hosted migration/readback/activation remain separate gates. No feature was
enabled and no issue is closed by this server-only slice.

Model the Domain shaped one monotonic eligibility fact on the canonical profile.
Sequence Work into Verifiable Units kept this server slice separate from native
adoption/retry and from activation. Independent review and guarded merge belong
to the captain. The author does not approve or merge this PR.
