# Combined profile response reconciliation

Original integration base `f5c83cd88a0af56dc8154a89c6ea4f75d9c518ce` remains the
lane base. Previous published head was
`70b2f25646f1d05445704ae25e3d791a2a913568`. Fetched current integration was
`927740efd7911847bc6deca1c0586905b170ff7d`. The normal reconciliation merge and
verified source is `626e38eeacaa7019c01125a7dd0b321963dc43f0`. No rebase occurred.

## Concrete overlap and fix

Integration added the deletion admission and recovery contract, app manifest and
Apple name command. The generated OpenAPI artifact conflicted where both branches
add their respective contracts. It was regenerated from the combined canonical
runtime once the projection fix and response description were settled. Deletion
statuses, retry headers and admission behavior were retained.

The combined API had one concrete response defect. GET /me projected linked
Apple identity, but PATCH /me and POST /me/apple-name returned null for the same
owner through their shared UserResponse builder. Three regression cases failed
on that combined source before repair. The name regression initially returned
503 because its new mock row was incomplete; correcting the fixture made it fail
on the intended null-subject assertion. [projection-red.txt](projection-red.txt)
records the corrected reproduction.

The fix reads the existing canonical identity through profile._apple_identity
before either permitted mutation, then passes it to the existing _user_response.
Invalid profile input still fails validation before the identity read. Unavailable
identity causes no profile write or name-command dispatch. PATCH retains
apple_identity_unavailable; the name command retains apple_name_unavailable.
No session-provider inference, subject cache or new response schema was added.

The native currency mutation ignores its PATCH body and then reads GET /me through
loadProfile, which validates the canonical subject. It therefore did not adopt the
incorrect null PATCH projection. The new name endpoint now has the same envelope
for a future caller. Its native journal and adoption flow are separate work and
were not implemented here.

## Current verification

- Focused API, profile, name and generated-schema checks passed **135 tests**,
  with **70 deselected**, **zero failures** and **zero skips**, in 7.05 seconds.
- Real isolated PostgreSQL, Auth and API passed **8 tests**, with **zero failures**
  and **zero skips**, in 2.80 seconds. They cover current-owner GET/PATCH projection,
  malformed and conflicting identities, signed Auth isolation, currency persistence
  with a concurrent name edit and unauthorized refusal, and name retry/relaunch,
  explicit clear and deletion-admission refusal. Name responses preserve the linked
  subject after initial save and retries. The shared request error tests prove
  unavailable projection dispatches no name command and changes no profile.
- The free ten-file mocked harness passed **272 tests**, with **zero failures**
  and **zero skips**, in 8.25 seconds.
- Combined modularity reported **zero violations**. Whitespace checks passed.

Results are committed in this directory. Python used the existing isolated
3.11 environment and PYTHONPATH=web:src:. Real tests used the root-granted exclusive
PG60332 lease and root-owned isolated Auth60331. Only local synthetic configuration
was loaded. Tests cleaned their own fixtures. The lease was released without
stopping, resetting or changing the shared stack.

The first broad deterministic run passed 134 and failed one old currency test
because its scripted gateway had no identity source. Its fixture now explicitly
reports confirmed absence through the canonical reader; no production guard was
weakened. The final 135-test result above includes it.

## Remaining proof and ownership

The prior actual currency reconciliation changed shared native source. Earlier
package, live Auth/API/Keychain, model and UI evidence remains historical evidence
at its recorded source. This later merge adds no native source changes, but it
cannot close the pending combined native proof from that reconciliation.

Counsel owns the Mac and simulator. This worker ran no Swift build, package test,
simulator or physical-device action. After that slot is released, the captain must
verify the combined session package and affected models, zero currency dispatch
while Apple validation is held or an unknown linked session needs reauthentication,
and the affected Apple recovery and currency English/Spanish simulator journeys.
Independent review and terminal exact-head CI remain required before merge.
Physical Apple/provider authorization, hosted acceptance and activation remain
open. All flags and hosted settings are unchanged. This worker owns no background
processes and stops after publishing; the captain owns the single merge queue.
