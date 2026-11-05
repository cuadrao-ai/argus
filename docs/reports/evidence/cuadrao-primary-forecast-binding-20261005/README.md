# Connected forecast currency binding: C3 source handoff

Base: `87a616ef0` (C1), including recovered UI dependency `56b6de7`.
Branch: `codex/cuadrao-primary-forecast-binding-20261005`.
Issue: #820. This is source preparation; it does not close #820 or claim release acceptance.

The forecast derives available choices only from `projection.currencies`.
`CurrencyPresentation.selectedCode` retains an available explicit choice, then
uses an available canonical profile currency, then a sole currency. Multiple
currencies without either valid choice remain unselected with a choice prompt.
An unknown currency remains selectable. Existing chart eligibility and exact
money formatting retain unknown versus zero and the selected payload's exponent.

The same selected forecast payload supplies the chart, balance, income, bills,
transfer effect, net change, shortfall and included-account explanation.
The account selection command, scheduled occurrences and management sections
remain unchanged. Selection is transient. Profile identity or Plan model changes
remount its state owner; a missing projection also removes that owner. The
connected personal forecast is replaced by the household router's distinct
surface when household context is active. Currency and account-selection changes
remount chart inspection. Date and point-balance changes clear its inspected index.
A primary change follows the new preference only without a valid explicit choice.

Design comparison: keeping only explicit choice and deriving the effective code
avoids copying Profile's durable preference into local state. A second stored
effective choice would need synchronization on every profile refresh.

Checks completed: `git diff --check` and `python3 scripts/check_modularity_budget.py`
pass. Synthetic selection checks were added to `CurrencyPresentationChecks.swift`;
`python3 ios/DesignPreviewTests/run_currency_presentation.py` is the future runner.
It has NOT been run. No Swift compile/test, Mac preview, simulator, device,
service, provider, environment or hosted operation was started.

Pending under the captain's runtime lease: compile and run synthetic checks,
then verify one chart and matching readout, currency switch inspection reset,
account-selection reset, profile/identity/context reset, unknown and known-zero
states, exact exponent and locale, and unchanged account selection/occurrences.
Synthetic helper checks do not establish SwiftUI or connected acceptance.

Delivery order is recovered UI, C1, then C3. Do not mark C3 ready before its
parents land. Rollback is this binding commit.
