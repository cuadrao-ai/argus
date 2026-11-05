# Recording lane decision response

September 28, 2026. Response to the founder's eleven-question summary of PR #724.
This publishes prior decisions and lead recommendations; recommendations are
not retroactively labeled founder approvals. The MVEE remains experience owner.

| Question | Answer and authority |
| --- | --- |
| 1. Save confirmed money facts? | **Yes, settled.** The MVEE explicitly owns durable confirmed financial records. Its ingestion section now names the limited supersession of historical Decision 8. Chat retention and personalization-memory exclusions do not change. |
| 2. Change starting-balance date later? | **Yes, approved editing direction.** Balance date is an optional account detail. Define correction/versioning, affected-history preview and as-of/timezone handling in the contract. A date change must not silently reinterpret existing activity. |
| 3. Ask whether an earlier/same-day purchase was included? | **Yes, settled.** Ask when inclusion is unresolved for an affected balance check, including each account leg where needed. Do not restrict review to same-day records or ask redundantly when confirmed provenance already answers it. |
| 4. Show an unexplained gap? | **On the account as an unexplained balance difference, not income/spending.** Keep confirmation-time provenance and remaining discrepancy distinguishable. Recording missing activity may explain it; equal amounts alone do not prove a match. |
| 5. Archive with money still present? | **Yes. Preserve balances and obligations in totals.** The frozen template's Manage accounts explicitly says this. PR #724's proposed warning that archiving removes balances from totals conflicts and must be corrected. Archive tidies navigation; it does not dispose of assets or discharge debt. |
| 6. Personal share or full shared-account amount? | **Personal share; household counts the same authorized account once.** Asset ownership controls and no-double-counting are approved. The lead recommends full-account detail with an explicit personal-share readout; do not invent 50/50 ownership or infer visibility from ownership. Where account ownership data is absent, the production contract must resolve it explicitly. |
| 7. Peso/dollar transfers? | **Keep blocked in the first slice.** No implicit FX and no combined-currency total are approved. A later actual-amounts-on-both-sides contract is separate; recording a refund in its received currency does not authorize a cross-currency transfer engine. |
| 8. Duplicate-looking statement rows? | **Lead recommendation:** hold flagged/uncertain rows for review; let the user explicitly confirm independent clean rows. Preserve batch progress and linked-record atomicity. Do not auto-drop equal amounts or commit half a transfer. Exact partial-batch behavior remains a proposed contract. |
| 9. Stale confirmation? | **Lead recommendation:** write nothing; refresh, explain changed effects and ask for confirmation again. Preserve the user's edits where safe. The interaction follows the existing review/confirmation boundary; concurrency mechanics require real database proof. |
| 10. Fixed/editable categories? | **Optional custom labels are already approved for Business.** Fixed-only everywhere conflicts. Lead recommendation: localized defaults and stable custom-category identity, separate from arithmetic-driving activity kind. Rename must not change money meaning. A catalog is not needed to create an account without activity. |
| 11. Guests saving accounts? | **No, founder-locked September 28.** Follow the [MVEE guest access boundary](../argus-minimum-viable-ecosystem-experience.md#guest-access-and-registration). The product decision is settled; server enforcement and registration/return-to-action mechanics still need contracts. |

## Engineering disposition

Integer minor units, atomic linked movements, revisions, idempotency and stale
preview protection are sound proposed directions. The reference model proves
examples, not production locking/RLS/retention. “Derive totals” does not prohibit
a later performance cache derived from the same owner, nor permit recalculation
to erase confirmation-time audit evidence. Neither a storage design nor the
whole reference model is approved for automatic promotion by this response.

Reconcile the specification and focused proof now. A create/reopen/edit slice
should not be held for categories, transfers, listing feeds or bank connections
it does not use. Before runtime work, bind API/data ownership, guest policy,
opening-date correction behavior and a database acceptance gate in its assignment.

## Sources

- [MVEE](../argus-minimum-viable-ecosystem-experience.md): account setup, archive, balance/refund review, spaces, ingestion, household.
- [Reconciliation handoff](../argus-account-balance-reconciliation-handoff.md).
- [Mobile archive](../../reports/mobile-design-lock-2026-09-28.md): `account-management.js` states that balances, history and obligations remain in the financial picture.
- [Historical Decision 8](../../archive/2026-09-17-argus-grounded-finance-roadmap.md): typed figures already remained inside conversation messages.
- [Proposed contract #724](https://github.com/lagarcess/argus/pull/724), head `720aad3fdee1357e3dbe5c928176a6e458b01b0d`.
