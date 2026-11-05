# Home checkpoint, October 24, 2026

Status: local Home implementation baseline locked after the bounded sweep. No new Home layout or month-picker blocker found in the checks below. Known pending design decisions are not resolved by this checkpoint. No push, handoff, deployment or backend change.

## Preserved scope

The baseline is commit `9d1b6bc3e` plus the month-picker fix committed with this record. The existing Home guide, money cards, pending-work checklist, empty states, inline save recovery and invitation completion behavior stay in place.

The month picker retains its existing control even when only one month is available. It lists the service-supported history through the service's current month, with no future rows. Missing, invalid or future earliest-month values fall back to the current month. Bulk uploads may extend the supported history when the service returns an earlier bound. This sweep did not exercise a real bulk-upload pipeline.

## Final sweep evidence

- Actual local server: http://127.0.0.1:4387/biz with synthetic fixtures.
- Desktop checked in Spanish/light, Spanish/dark and English/light. English/dark evidence captured before restoring Spanish/dark. Month menu lists October 2026 alone for the current fixture and Escape returns focus.
- Phone requested at 390 x 844; the browser rendered a 400px document width. No horizontal overflow at that actual width. Checklist, stacked money cards, visible zero amount, settled explanation and Add action inspected. This is not proof at 390px or on a physical phone.
- Tablet checked at an 820px requested viewport. Checklist and monthly figures stack above the paired money cards. Desktop cards retain aligned outer edges.
- Original language, appearance and default viewport restored. The proposed Home layout was not applied.
- 123 tests passed across seven month-close and workspace-preview suites. Coverage includes supported month bounds, cross-year history, focus/selection, unknown versus zero amounts, empty-state actions, failed marks/retry/Undo, per-document error isolation and invitation completion in EN/ES.
- Scoped ESLint for the month fix and git diff whitespace checks passed. This is not a full-build, full-typecheck, hosted integration or real delivery claim.

Evidence folder (outside Git): `/Users/garces/.codex/visualizations/2026/10/22/01a164fb-0899-7500-a387-b81e8f79f1a3/home-checkpoint/`.
Month menu before/after: sibling `month-picker/before.png` and `month-picker/after.png`.

## Pending decisions, no implementation authority

| Area | Direction discussed | Still to decide |
| --- | --- | --- |
| Mi Negocio | Use the existing Business menu as an entry point | Inventory existing Business page tabs, settings modals and record dossiers; assign one owner and one destination per task before moving anything |
| Electronic invoicing | Separate capability setup from basic workspace readiness | Choose its menu entry and existing dossier destination; distinguish starting setup, required checks to issue, waiting and confirmed active state |
| Collaboration | Separate access management from the initial document task | Choose the existing access-management destination; retain invitation-created completion, pending acceptance and no-access-yet distinctions |
| Home guide | Focus on adding a first document and reaching useful information | Decide when guidance recedes and what the combined wheel should become; do not change completion semantics or remove the wheel yet |
| Color hierarchy | Reserve emphasis for a primary action and confirmed positive outcomes | Resolve the broad Quiet-green rule, routine Review/See links, duplicated completion emphasis and green In progress before changing shared button classes |

Existing container ownership remains authoritative until that mapping is reviewed. A menu can expose an entry and a status; detailed work should reuse its existing surface where suitable. This does not authorize a new Business hub, new services, duplicate forms, role changes or new activation logic.

The separate file-based Home layout sketch remains unverified and unapplied. Browser policy blocked opening that local file. It is not checkpoint evidence or an approved design.

## Outside-scope finding

The existing development overlay displayed six stored issues. The inspected issue reports duplicate key `exp-gas` in `TransaccionesRecords.tsx:89`. Its stack points to the Transactions table. No Transactions changes were made, and the cause or remaining five issues were not investigated in this Home-only sweep. Do not describe the whole application as error-free.
