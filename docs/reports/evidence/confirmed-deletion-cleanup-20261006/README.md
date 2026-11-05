# Confirmed deletion cleanup: source handoff

Base: `8146d16e90633eb543781f8882665482f0d5dca9`, guarded #875 landing.
This is a new isolated actor-boundary slice. Independent runtime QA passed at
`f787ca63af9ba4e6355357ed5e1a8ead5a3dfb21`; the #875 worker and its historical
QA evidence are unchanged. The [published independent bundle](independent-review/README.md)
owns those results and the baseline-gap reproduction. Current integration is
still the original base, so no reconciliation merge is needed.

## Boundary and source change

`acknowledgeConfirmedAccountDeletion(_:cleanup:)` now requires a synchronous
throwing `@Sendable (UUID) throws -> Void` callback with no default. Inside the
existing actor, it acquires the mutation guard, checks absent session and pending
proof, validates completed journal/receipt owner, command and initiating revision,
invokes cleanup with the journal's exact UUID, then removes only that record.
There is no await or other suspension between admission and the effect. There is
no callback-free overload and no new cleanup journal.

The existing completed record owns cleanup retries. A thrown cleanup error leaves
it intact. If acknowledgement storage fails after successful cleanup, the same
record survives; retry must tolerate the already-missing directory. Relaunch
readback still derives the receipt from that record. Beginning a new account's
adoption already owns the mutation guard and cannot be interrupted by cleanup.

The [architect sketch](design.md) records the two alternatives and selected shape.
This is not the final app adapter. Receipt-store paths, UI and actual Application
Support directories remain untouched.

## Precise gap and prepared proof

The previous caller sequence is `clear A files; await acknowledge A receipt`.
A completed, then B signed in before that caller ran. The actor rejects stale A
at acknowledgement, but A's files have already been removed. The API cannot undo
an effect that the caller performed before admission.

[BaselineDeletionCleanupGapTests.swift](BaselineDeletionCleanupGapTests.swift)
is prepared for the exact #875 source test target. It uses the production session
actor with synthetic HTTP responses, unique temporary A/B directories and actual
filesystem operations. It observes A removal before stale acknowledgement rejects
while B and its files survive. This is an intentional historical-API baseline
probe, not a current caller. Independent QA ran it on exact 8146: one passing probe reproduced the unsafe
cleanup-before-rejection sequence. This is evidence of the old gap, not old
boundary correctness.

Current package test source checks:

- A completes, B adopts, stale A callback has zero A/B filesystem effects.
- Valid completed cleanup receives the journal UUID; missing directory is
  idempotent and an unrelated user's temporary directory survives.
- Callback failure keeps files and the completed obligation; relaunch retries
  cleanup without another deletion POST.
- Successful cleanup followed by acknowledgement-storage failure keeps the
  obligation; repeated idempotent cleanup finishes without another deletion POST.
- Active B SDK adoption rejects cleanup before effects and preserves pending proof.
- Accepted 202, uncertain deletion and ordinary sign-out cannot authorize cleanup.

All fixtures live under unique temporary directories. No actual Application
Support data, provider, hosted, PostgreSQL or paid operation is exercised by them.

## Caller migration and verification limits

The executable package caller now passes an explicit test-only no-op callback
where no filesystem obligation exists. New filesystem cases supply real cleanup
callbacks. The unsafe production signature is removed.

#875's archived live harness remains immutable historical evidence. Its
[migrated copy](LiveDeletionTests.swift) passes an explicit no-op callback on its
stale-owner denial path, which has no filesystem obligation. Independent QA exercised that copied harness against f787: one current local
SDK/API/Auth/PG case passed with no skip. The old #875 SDK result is not used as
proof of this new boundary. The historical baseline probe is the only
intentional callback-free reference in this new evidence folder.

Source/static review is not runtime proof. Independent f787 QA executed 174
package cases (170 passed, 4 existing opt-in skips), filesystem 6, deletion 20
and one migrated local SDK/API/Auth/PG case, with no focused/live skips or failures.
These are separate overlapping runs, not a summed count. No app compilation,
app UI, receipt-store, actual Application Support, hosted/provider or physical
phone acceptance is claimed for this slice. Analytics completion was synthetic.
No Mac, PG, hosted, provider or paid calls ran while authoring or publishing.
Root owns final context/publication review, terminal CI and guarded merge.

## Author checks

Independent bounded source review of the actor and six new filesystem cases found
no concrete blocker. It ran no compilation or tests. Python modularity and diff
whitespace checks pass; source fingerprints are recorded for the queued verifier.
The callback boundary changes one production method, with no vault, server,
migration, app UI, receipt-store or actual user filesystem change.


## Fixture correction and publication

The initial b77 candidate failed Swift 6 compilation before tests because its
new denied-state fixture transferred a ternary `[String: Any]` body to the actor.
The fixture-only f787 commit uses separate literal branches. Production actor
object `8720b2c26da7c3955bc5b291eef423f3c94f52dc` is unchanged, as are denied-state
assertions. The failure log and exact correction diff are retained in the bundle.
No zero-test or failed run is acceptance evidence.

All 16 raw bundle payload hashes and 52 package source objects/fingerprints were
verified before publication. The baseline and migrated live source match the
committed copies. Only the documented test port allow-list differs in the live
package copy. Published text normalization has an explicit raw-to-published hash
map; the original manifest is retained. Production source and original #875
evidence are unchanged by this evidence commit. Fresh static checks pass.
