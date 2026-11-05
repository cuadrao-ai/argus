# Account balance reconciliation — backend handoff

**Status:** Founder-approved experience constraints, September 27, 2026.
**Not assigned:** production implementation, schema, API, migrations or deployment.
**Experience owner:** [MVEE account activity and balance checks](argus-minimum-viable-ecosystem-experience.md#account-activity-and-balance-checks).
This note captures engineering obligations and open choices; it does not replace
[documentation authority](../DOCUMENTATION_AUTHORITY.md), API_CONTRACT or DATA_MODEL.

## Required truth

A starting balance is not income. An observed balance is evidence of a position
at a time, not proof of a complete transaction history. Do not treat recording
order, an upload time or today's date as a substitute for the source's as-of date.

Example: opening 10,000; known spending 2,000; expected 8,000; observed 7,500.
Confirmation records a -500 unexplained balance adjustment. Known spending stays
2,000. History preserves expected/observed amounts and the difference, currency,
source, as-of date, confirmation provenance and later correction lineage.

If the missing 500 expense is subsequently supplied for the period covered by
that check, spending becomes 2,500 while the balance stays 7,500; the unexplained
portion is reconciled, not charged again. A genuinely new 500 expense after the
check reduces the balance to 7,000. Equal amounts alone cannot identify matches.
Partial matches must preserve the remaining unexplained difference. Never label
an adjustment resolved merely because the arithmetic happens to match.

## Contract work needed before implementation

- One authoritative owner derives expected position, discrepancy, reconciliation
  state and affected summaries for web, iOS and Android. Clients render typed
  facts; no independent client arithmetic for committed truth.
- Define exact money representation, precision, currency identity and debt signs.
  No implicit FX or mixing amounts across currencies.
- Define observation/as-of versus posting/recording dates, timezones, ordering,
  duplicate ingestion and opening-balance provenance. Distinguish unknown, zero,
  no difference, unexplained adjustment and asset valuation change.
- Define the durable relationship among observations, adjustments and subsequently
  matched transactions, including split/partial matches and transaction edits.
  Preserve audit history; avoid silently rewriting what was confirmed earlier.
- Review/confirm must handle stale previews and concurrent writes, owner/household
  permissions, idempotent retries and atomic paired transfers/payments.
- Corrections, removal and restoration must update affected account legs and
  summary coverage consistently. Determine when a later confirmed observation
  remains authoritative, when its discrepancy is recalculated, and what requires
  renewed review. Define retention/recovery separately from conversation deletion.
- Keep observed-position truth separate from spending/budget coverage, including
  Home, Plan and Updates. Unknown coverage must not create confident alerts.

## Acceptance scenarios for the future lane

Use synthetic fixtures for positive/negative/zero differences, unknown prior
balances, overdrafts and debts, multiple currency precisions, partial missing
activity and matching versus genuinely new activity. Include overlapping statement
imports, duplicate retries, backdated corrections, two balance checks, paired
transfer removal/restore, and concurrent confirmation against stale expected
balances. Verify both balance and spending/income summaries and retained provenance.

## Disposable sketch boundary

The local demo previews the difference and keeps confirmation-time metadata on
an in-memory balance entry. Its existing replay applies absolute balance snapshots
in recording order. A new account-level review now asks whether late-entered
activity was already included in a preceding checked balance, including each leg
of a paired movement. The preview can preserve that checked balance while
including the activity in spending. It does not infer matches or settle residual
adjustment accounting, historical ordering, persistence or production conflicts.
The UI lock must not be read as evidence that reconciliation is implemented.

## Refund and linked-plan acceptance additions

- Cover partial/multiple purchase refunds, absent original purchases, received-date
  budget attribution, credit-card credit balances, same-currency returns to another
  account, and explicit foreign-currency received values without inferred FX.
- Keep refunds out of income. Show gross purchases and refunds when net spending
  is negative; do not hide the refund by clamping reported money to zero.
- Corrections/removal/restoration must preserve purchase/refund links and prevent
  linked refunds exceeding the surviving purchase. Never orphan a refund silently.
- Separate loan principal, interest and fee reversals. A generic purchase refund
  must not guess these portions. Check balance can record an unexplained position,
  but cannot claim that its underlying loan history is reconciled.
- Verify a linked expected payment is counted once across actual cash and the
  forecast. Refunds do not silently reopen the obligation. Changes to linked
  actual records require revalidation, not a sticky completed boolean.
- The sketch rejects unreviewed late activity behind a balance check. Document
  import and expectation shortcuts must hand off to account review for this case.
  Production must support a coherent batch review with the same authoritative
  reconciliation owner rather than bypassing the check.

## Space reassignment handoff

Moving an account between private spaces is organizational, not a financial
posting. Preserve account/entry identity, observation and correction lineage,
removed-entry recovery, currency, source provenance and paired-account links.
Use one server-owned operation with source/destination authorization, a stale-
preview check and atomic commit. Recompute scoped budget/search/forecast views
without duplicating entries or turning transfers into income. The template
blocks linked accounts rather than attempting partial moves. Production needs
an explicit disposition for grouped transfers, shared access, document links,
loan associations, open drafts and plan references. Returning an account to its
previous space undergoes the same current-state review.
