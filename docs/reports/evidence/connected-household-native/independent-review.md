# Independent review: canonical Household + connected native shell

Verdict: changes requested. Three concrete findings.

Reviewed exactly `631d405142435d059ab6ef419f8235bf0ad52947..c888acec2e43e0e051736708dfd1ec0197b121f9` in `/Users/garces/.codex/worktrees/connected-household-native/private-alpha-next`. The parent's unstaged `docs/specs/argus-execution-board.md` was excluded. This is one finished-diff review, not a release-readiness claim.

## Findings

### 1. [P1] Check a financial receipt before rejecting its old Household generation

File: `src/argus/domain/household/financial.py:203-204`.

An expense can commit while its response is lost. If the administrator then creates an invitation or changes another account's share, `households.version` advances while this actor's membership and all grants for the expense remain valid. The exact saved financial envelope still carries the earlier version. `money()` raises `StaleVersion` before reading its existing receipt. Native `HouseholdModel.retry()` treats that 409 as a definite failed command and clears the original journal (`ios/ArgusFoundation/Household/HouseholdModel.swift:171-172`). The user cannot recover the successful original outcome through the promised same-body/same-key retry and may record the expense again under a new key.

Independent deterministic reproduction used the actual `money()` method with a mocked current scope, owner records and committed receipt: membership and edit access were unchanged, current generation was 2, saved generation was 1. Result: `StaleVersion`, with zero receipt lookups. The same original activity body/key with generation 2 replayed the receipt. No database was used.

Smallest safe fix: retain the current incarnation check and live dependency/edit authorization before any protected replay; look up and validate the same-key receipt next. Apply the expected Household generation check only when no receipt exists and a new preview/write would be admitted. Test a committed response-loss retry after an unrelated generation bump, and preserve denial after departure/rejoin or withdrawal.

### 2. [P2] Keep archived shared money in Household positions

File: `src/argus/domain/household/projection.py:102-103`.

`positions()` skips archived accounts even though they remain explicitly granted and appear in the Household account projection. Archiving is organizational in the existing contract (`docs/API_CONTRACT.md:6536`, `docs/DATA_MODEL.md:1929`); it changes neither balance nor inclusion in canonical totals. Archiving a shared cash/asset account silently reduces the Household total; archiving a shared debt inflates it. An archived unknown account also disappears from `unknown_count`, making an incomplete picture appear complete.

Independent in-memory reproduction: the same archived shared checking account with DOP 1000 remained `net_worth_minor=100000` in canonical Recording Home, while Household `positions([account])` returned `[]`.

Smallest safe fix: remove the archived-account exclusion and retain the same canonical position/share calculation, currency separation and unknown counting for every authorized account. Add a focused archive/restore case that includes known money and an unknown account.

### 3. [P2] Preserve deletion-safe recipient membership history in the new FK

File: `supabase/migrations/20261001120000_household_consent_recovery.sql:18-19`.

The new `(recipient_membership_id, household_id)` FK has default `ON DELETE NO ACTION`. The landed `household_members.user_id` FK still cascades from `auth.users`. When Alice has granted an account to Bob, deleting Bob attempts to delete Bob's membership while Alice's grant still references it. Leave/removal/closure only sets `revoked_at`; the FK continues to restrict deletion after departure and closure. The deletion therefore fails instead of retaining Alice's legitimate canonical records under the established deletion-safe identity contract. This regression exists for an ordinary recipient and does not require deleting an active administrator.

Evidence: direct inspection of the landed and extension migrations plus `_end_membership()` / `_close_locked()`; the named recipient grant survives revocation and its referenced membership is subject to user deletion cascade. I did not execute PostgreSQL deletion in this review.

Smallest safe fix: give the membership-bound grant FKs an explicit deletion disposition compatible with the existing user-deletion behavior. Cascading the obsolete authorization grant when its membership is deleted is a bounded option and does not touch another owner's financial account/activity. If preserving grant audit rows is required, revoke and clear only the membership reference atomically with a compatible FK/check. Verify recipient deletion after leave and after close while the remaining owner's financial history survives.

## Scope and evidence limits

Read the repository AGENTS/review-proportionality rules, Argus review skill, product and documentation authority, relevant MVEE and locked Household policy, architecture/design boundaries, amended API/data contracts, native setup and the finished source/test/migration diff. The authority map takes precedence over the review skill's stale roadmap pointer.

The implementation retains the canonical Household store, separates acceptance from financial consent, binds grants to current owner/recipient incarnations, checks old/new/refund/reversal dependencies, attributes Recording writes to the actor and preserves owner-qualified money. The projection redacts private counterpart IDs and nullable author fields; Personal contracts remain separate. No speculative future features or broad redesign are requested.

Independent test command used the specified existing Python with `PYTHONDONTWRITEBYTECODE=1`, `PYTHONPATH=src`, persistence/checkpointer memory modes, blank database/provider variables and pytest cache disabled:

`tests/household/test_household_domain.py`, `tests/household/test_household_lifecycle.py`, `tests/financial_accounts/test_household_projection.py`: **8 passed, 2 skipped in 0.18s**. The two skipped cases require PostgreSQL. Two additional bounded in-memory/mocked reproductions produced the finding evidence above.

No services, device/browser work, caches, hosted/provider/data mutations, installs, source edits or remote/PR changes were performed. Captain-owned PostgreSQL/API/native/fault/session evidence was not represented as independently verified here. Native concurrency behavior was inspected, not rebuilt or run. The temporary diff was removed; no process remains active. Report ownership is relinquished to the parent.
