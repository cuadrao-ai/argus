# Business lifecycle UI continuation, October 18, 2026

This continuation starts at `0f48eae0d5e7e949661c4d86131d8d9b2a9e52b3` in the
existing draft PR #1222. The fetched integration base remains
`651870a54be4e5506dbb38f3902fef1a97eef8df`. Integration was refreshed before the
checkpoint and did not advance. No merge or rebase was needed.

## Result and retained hold

Required continuation step 5 is wired and locally verified. This remains a held
WIP delivery. `require_lifecycle_ready` still unconditionally refuses lifecycle
and transfer requests, and global account deletion stays off. No hosted SQL,
staging change, provider call, real email, merge or deployment ran. The receipt
gate, independent final Eval and Rafael's permission retest remain with root.

The prior backend orchestration and transfer successor evidence remain intact.
Their older unmounted-UI status is superseded only by this continuation.

## Actual UI and authority

The actual account-deletion dialog reads the authenticated Business space list.
Each current-owner Business gets Iris's exact warning and its own close and
transfer links. Two-Business DOM and browser cases verify distinct target IDs.
Discovery failure keeps deletion blocked. Personal and guest behavior retain the
existing Business build gate.

The held lifecycle API now supplies the current owner's open Businesses and
eligible transfer members. It derives ownership from `current_owner_id` and the
current actor's live grant. Eligibility calls the existing transfer authority,
including Editar, confirmed identity and absence of a competing open Business.
No custody identity supplies acting-person authority.

The close and transfer routes open the actual existing dialogs. The close
journal keeps the same key for the same uncertain command. The existing export
component is reused unchanged. Its original date inputs require an explicit
1-to-366-day period. A second-owned-Business test proves its original export API
receives the intended grant and dates. No export implementation changed.

Lifecycle command routes render before workspace bootstrap. Ordinary Business
entry checks held lifecycle discovery before creating a missing workspace. A
closed-only current owner sees their closed list and can reopen. Readiness 404
keeps the existing workspace usable and adds no Business-creation POST. Synthetic
preview sources make no lifecycle API calls. Account-boundary tests still reject
late results and clear the previous person's workspace.

The close screen starts focus at the warning so a phone does not jump past it.
The export form and confirmation form are siblings, with no nested form. Long
multi-Business deletion content scrolls inside the viewport.

## Member close notification

The close transaction queues one row per close instant and live confirmed
registered member. Revoked or expired membership is excluded. A failed queue
rolls back the close and its command receipt. Replays and concurrent closes keep
one event per recipient.

The sender reads `business_closed_email.generated.json`, generated from the
existing canonical shared layout. Its approved Spanish subject and body remain
unchanged. HTML escapes inserted values once; plain text keeps literal names.
Dates use `America/Santo_Domingo`. Postal configuration remains required.
The already imported shared-email dependency through `eba4e8506` contains all
required close-template changes. A semantic comparison through PR #1226 head
`6e00e5d1a6a8d27c41be55ffb9012ee142e2bbd8` found no further close-template delta,
so no unrelated email or invite change was imported.

The existing Resend sender delivers only after the close transaction commits.
A durable first-attempt timestamp, frozen payload and stable provider key survive
an uncertain response. Automatic retry stops after 23 hours. A command replay
retries the same pending queue. Reopening suppresses unsent notices for the old
close generation. No expiry or transfer-mail behavior changed.

Forward migration `20261018080009_business_close_mail.sql` owns the service-only
queue. RLS and explicit grants exclude browser roles. Departing owners and
members lose their personal close-mail transport before account settlement.
Custody detachment removes scoped close transport, and Business purge cascades
it. The actual local catalog supplied both new FK rows and the unkeyed owner-ID
entry in the canonical deletion census. No earlier migration changed.

## Verification

All database proof uses the lane-owned `business_close_ui_testdb`, cloned from
the preserved `business_close_testdb`. Only the owned clone received forward
migrations 080005 through 080009. The root `postgres` baseline and source fixture
were not changed. The test process disabled project dotenv loading and removed
provider credentials. Auth, Storage and SMTP remained fake. Python used the
shared read-only 3.10 runtime. No environment or local configuration file changed.

The combined backend run passed 331 tests with the same 3 existing local-Storage
skips. A final service-only queue permission case passed separately. The Business
web regression run passed 240 tests across 44 files. The refreshed browser run
passed all 14 desktop/phone fixtures, with two additional warning-first captures.
The exact pushed head and remote CI snapshot are recorded on PR #1222. Focused
checks include close/list/reopen, transfer, the complete deletion/custody/purge
regression set, current-owner discovery, atomic queue failure, fake SMTP retry,
concurrent close, anonymous/browser-role refusal, departing owner/member privacy,
phone warning focus, two-Business deletion, explicit export scope and both
readiness states. TypeScript, ESLint, Ruff, generated email checks, whitespace,
branch ownership and the current-integration modularity budget also pass.

Browser fixtures cover close, request transfer, empty eligibility, access,
closed-only entry, readiness off and the actual two-Business deletion dialog at
1280 and 390 pixels. All API paths are intercepted and external navigation is
blocked. GET opening performs no mutation. Each fixture has no page error or
horizontal overflow. These are synthetic local UI observations, not real Auth,
hosted API, Storage or customer acceptance.

Screenshots and the full browser request ledger remain outside git at the
root-assigned evidence location.

`/Users/garces/.codex/visualizations/2026/10/16/01a1430c-fce8-78b1-a002-a704ae804d29/cuadrao-sprint/business-close-ui-completion/`

The ledger is `summary.json`. The warning-first phone capture is
`close-start-390.png`, and `delete-390.png` shows both actual deletion warnings.
These local captures do not satisfy a hosted release gate.

## Root handoff

| Required continuation item | Status |
| --- | --- |
| 1 through 4. Retained custody, identity cleanup and day-30 purge | Inherited committed backend proof, retained |
| 5. Actual warning, close/transfer, closed listing/reopen and member email | Implemented and locally verified in this continuation |
| 6. Three receipt runs, independent final Eval and Rafael permission retest | PENDING, root owns |
| Readiness, global account deletion, merge, hosted migrations and staging | HELD |

PR #1228's unfinished pending-invite changes remain separate. The eventual
combined acceptance must still prove the new owner can resend an invitation and
the former owner with Editar cannot. No new invite work is included here.

The scoped outbox and journal apply Make Operations Idempotent. The discovery
path applies Model the Domain by keeping current owner, custodian and actual
actor separate. No model-facing prompt or schema description changed. No paid
measurement ran. Independent final review remains blocked on the root-owned
receipt and reviewer gates, rather than being replaced by this writer's tests.
