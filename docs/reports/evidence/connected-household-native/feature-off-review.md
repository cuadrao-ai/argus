**CLEAN — no remaining actionable finding in the confirmed feature-off class fix and its bounded follow-ups.**

Reviewed head: `c38e4d107fd983cd95d5adf703513b913e443b0f`.
Base: `fda990f860d15a078fd750a74f9104708e3fc8a1`.
Tree: `/Users/garces/.codex/worktrees/connected-household-native/private-alpha-next`.

Reviewed the availability delta through c676, the narrow 429 retry delta through b30, then only the request-scope correction b30..c38. Unchanged financial ownership, backend, migrations and prior acceptance were not reopened.

The typed server `households_unavailable` response owns native availability. Controls, routed Household destinations and management/editor sheets derive from the same model state. Discovery gates initial exposure; the persistent shell presenter owns foreground/authenticated-identity re-probes. Disabled responses clear protected reads, invitations and editors, invalidate delayed reads, and return the shell to Personal while retaining actor-scoped saved selection and exact pending journal bytes. Recovery requires an explicit write retry. Generic network/403/404 and invalid-invitation failures do not imply membership loss; scoped membership loss still clears its selected protected state and persisted selection.

Two bounded recovery cases were considered:

- **429:** the all-4xx journal-clear rule already existed at fda, so this was not called a c676 regression. The captain included its reachable pending-retry case in the authorized class fix. b30 excludes 429 from definitive clearance, preserves the original body/key and pending journal, releases busy state, and leaves submission explicit. Its focused regression checks those behaviors.
- **Resolved P2, cross-household retry:** c676/b30 applied a saved H1 command's `not_a_member` response to the actor's currently selected H2, incorrectly removing H2's valid saved selection. c38 passes captured request household context through read/editor failures and derives retry scope from the saved path. Membership/access loss clears selection only when that failed scope matches the current selection; feature-off remains global. The new delayed-H1-command/select-H2/deny-H1 regression checks preserved H2 detail, snapshot, selection and reopen, plus terminal clearance of the rejected H1 journal. The parser reuses the existing financial membership-preflight interpretation and does not change journal bytes.

Touched contracts/tests: `docs/API_CONTRACT.md`, `ios/HOUSEHOLD_SETUP.md`; `HouseholdModel.swift`, `HouseholdActivityEditor.swift`, `HouseholdViews.swift`; `ios/FinancialModelTests/HouseholdModelTests.swift` and `ios/ArgusFoundationUITests/HouseholdUITests.swift`. No backend wire, ownership, persistence or migration contract changed. The changes remain proportional to the validated availability/recovery cases and add no client feature flag or duplicate state owner.

Evidence limits: independent static review of the committed deltas, relevant native routing/auth bindings and existing backend problem codes; no reviewer tests/builds/UI/API/Auth/Postgres/CI execution. Writer/captain separately report 14 production Household-model tests passing, the 64-test Session package with four opt-in skips, and reproduced failing assertions before the two recovery fixes. The captain reports real default-off native acceptance at b30 and owns exact-c38 off/on native/API/Postgres revalidation and final CI. Those reports are not independent reviewer verification or a readiness/deployment authorization.

No source, service, device, simulator, cache, database, environment or GitHub changes; no subagents or background reviewer processes started. Only this review report was written. No scratch remains. Ownership is relinquished to the release captain.
