# Household permission policy (locked 2026-10-01)

**Status:** Founder approved 2026-10-01 (Project orchestrator recorded).
**Owners:** [MVEE Household](../argus-minimum-viable-ecosystem-experience.md#12-household-collaboration-approved-minimum-capacity)
for consent and financial meaning; [execution board](../argus-execution-board.md#connected-spaces-and-household-lane)
for delivery; this file for the locked permission package.
**Flag:** `CUADRAO_HOUSEHOLDS_ENABLED` (default off).

## Locked package

1. **Creator administers** invitations and membership. The creator (or current
   administrator) may transfer administration or close the household before
   departure.
2. **Members** see the member list and may leave.
3. **Shared accounts start view-only.** Activity editing requires an **explicit**
   grant from the account owner.
4. **An edit grant does not** confer ownership, membership administration, or
   resharing rights. Owners retain ownership, sharing, and account-removal powers.
5. **Leave or removal** revokes membership and that member's account grants.
   Original owners retain records and history. Closing a household preserves
   financial history; it does not delete another person's accounts.
6. **Invitations** are revocable, single-use, seven-day links. Same-recipient
   acceptance retries remain safe (idempotent membership). Local lane
   invitations are synthetic; no email, WhatsApp, or external delivery is
   required for acceptance proof.
7. **Three separate operations:** create household ≠ invite ≠ share account.
   Accepting an invitation grants **membership only** (since the
   [October 2 lane locks](../argus-decision-log.md#october-2-2026-cuadrao-lane-locks),
   a household invite also admits the person to the beta) — never an automatic joint
   account, private-account share, money move, or private-space reassignment.

## Consent boundaries (unchanged)

Membership alone must not expose private accounts, documents, chats, or income.
Sharing is explicit per account. `ownership_share_bps` remains a financial fact,
never an access control. One canonical account/history; count its permitted
projection once.

## Out of this slice

Shared budgets/goals/debt plans, private-source contributions, Business/Custom
space lifecycle, live do-blitz/Resend delivery, #760 native shell ownership, and
physical-phone proof remain separate assignments.
