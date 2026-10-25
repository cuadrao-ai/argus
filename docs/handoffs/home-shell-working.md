# Home shell design working record

Status: local design only. No handoff, push, deployment or hosted flag change.
Base: fe233679257035ea2dce8998b510868be9989632.

## Deferred greeting and ownership integration, October 25, 2026

The approved Home greeting uses the viewer's local clock and the saved preferred
name already supplied by the account shell. It introduces no new profile field,
timezone service, auth behavior or API. Both languages and phone/desktop reuse
one greeting implementation. A browser-session sentinel contains only `1`; no
name or greeting text is persisted by this UI behavior. Actual account-profile
persistence and auth remain backend integration responsibilities.

The ownership backend batch is not merged or deployed. A later wiring change
must address `BusinessWorkspace.tsx`, currently around line 327: the directory
effect clears `chosenGrant` whenever the selected membership has role `owner`.
That treats every Owner membership as the default Business. A person who already
owns Business B and accepts co-Owner access to Business A must remain in selected
Business A. Do not infer the default Business from the role alone. This UI pass
records the dependency and does not change selection logic.

Hosted acceptance for a later authorized checkpoint must prove:

- A preferred name saved through the real profile API survives reload, sign-in
  and another device, and appears in Home. An absent name has no comma or fallback
  identity. Local preview text does not prove profile persistence.
- After accepting Owner access to A while already owning B, selecting A remains
  selected across reload and sign-in. A's records, actions, permission checks and
  invitation context stay scoped to A. Pending acceptance grants no access.
- Both languages, both themes and desktop/phone show the correct local greeting
  at a time boundary and after resume, without hydration errors or animation
  replay. Real auth and profile responses must be used for hosted evidence.

These are deferred backend requirements and hosted criteria, not a sent handoff,
backend authorization or release acceptance.

Local browser review on the existing port 4387 checked 1731px desktop and 389px
phone in Spanish/light and English/dark. The current afternoon greeting was
correct. Home navigation, desktop/phone changes and language changes did not
replay it, and neither width had horizontal overflow. The reviewer restored
Spanish/light desktop. Boundary, first-animation and reduced-motion behavior are
covered by focused automated tests; this is not physical-device or hosted proof.

## Approved sidebar behavior

The founder selected B with simple tooltips on October 23, 2026. This supersedes the earlier local overlay experiment.

Business desktop uses a docked 240px Expanded rail or a 64px Icons-only rail. An explicit toggle, shortcut or preference selection resizes the workspace over 200ms. Hover and keyboard focus show a tooltip without expanding the rail. Escape, outside clicks and focus in the page leave the docked rail unchanged. The saved choice controls both the toggle and settings. New Business defaults to Expanded; a saved Business hover value becomes Icons only. Personal preferences remain separate. Tablet and phone navigation retain their existing behavior.

The Model the Domain principle keeps the existing sidebar mode as the preference owner. No second overlay state remains. SidebarShell is restored to its baseline placement. The header keeps one toggle mounted so keyboard focus survives its transition.

Owned code: useMobileShell.ts, SidebarHeader.tsx, SidebarPreferenceModal.tsx, its ChatInterface.tsx call sites, and focused sidebar tests. The guide owns the approved interaction rules. Preserved untracked recovery and startup preview routes are outside this change.

## Work checklist

- [x] Read the affected subsystem and its state ownership.
- [x] Compare independent sidebar sketches and an interactive A/B preview. The founder selected B.
- [x] Record the throughput checkpoint.
- [x] Delegate implementation, then review the diff independently.
- [x] Run focused behavior tests and inspect the actual local application.
- [ ] Commit ordered changes. Skip until the founder requests a commit.
- [x] Verify the approved anchored shell with the dossier open and at narrow viewport sizes. No dossier redesign is included.
- [ ] Open a PR. Skip because this remains a private design iteration.

Blocking first steps were the founder's choice and confirmation of existing file ownership. One worker owned code and tests on the design branch. The parent reviewed settings read-only and edited docs only after the worker returned ownership. Shared mutable state was serialized by that ownership transfer. A single code worker was the smallest safe split because rail state, settings and their tests share one behavior contract.

## Local evidence

- 77 tests pass across business-sidebar-rail.dom.test.tsx, business-sidebar-shell.dom.test.tsx, mobile-shell-layout.test.tsx and sidebar-mode-state.test.ts.
- Targeted ESLint and whitespace checks pass for the implementation. The full typecheck remains blocked by existing repository errors; it is not a clean typecheck claim.
- Actual local browser measured Expanded at 240px and Icons only at 64px. Search and Home align at x272px expanded and x96px collapsed. This deliberate 176px reflow is the approved B behavior.
- Keyboard focus on Inicio shows the existing tooltip and leaves the rail at 64px.
- Sidebar preferences show Expandida and Solo iconos. A selection survives reload.
- Light and dark desktop inspected. Narrow viewport visual checks are recorded below; physical-device verification remains separate.
- Screenshots: /Users/garces/.codex/visualizations/2026/10/22/01a164fb-0899-7500-a387-b81e8f79f1a3/home-shell-20261023/docked-b

## Settings container audit

Existing approved rules already distinguish these containers. They have not been redesigned in this pass.

| Content | Container | Current owner |
| --- | --- | --- |
| Business data, team/access, receipt email | Business page tabs | BusinessSettingsPanel.tsx |
| Personal profile and preferences | Modal AdaptivePanel sheet on small screens, right drawer on desktop | ProfileMenu.tsx and ProfileSettingsPanels.tsx |
| Receipt, draft, email or expense detail | Non-modal record tray beside its list on desktop; full-page record on phone | BusinessPanel.tsx |
| Short pickers and account menu | Popover where space allows | Existing menu components |
| Destructive confirmation | Alert dialog | ConfirmDialog |

A child setting replaces its parent and offers Back. It does not create a second visible sheet. A record tray leaves the list usable; a settings drawer holds focus until closed. Sharing the right edge does not make the settings drawer a dossier.

Follow-up findings, not yet an approved settings redesign:

- Sidebar preferences opens through a separate ChatInterface callback and has no Back path to Preferences. Other nested settings use ProfileSettingsPanels.
- The flagged messaging-link preference mixes a personal linked number with a link to Business receipt controls. Confirm ownership before moving it. No provider change is included.
- ProfileSettingsPanels contains an unused business_name entry. The reachable Business name editor is already in the Business page.

## Right-edge correction, October 23

The founder clarified that the right edge moved left when the sidebar collapsed. The left-edge movement was correct. This is not a request to redesign the dossier.

Reproduced in the actual browser at a 1513px viewport. The 1200px canvas cap made its right edge move from x1472 to x1296 when the rail collapsed. The header used a matching width cap. The Fix Root Causes principle led to removing those caps in their shared owner instead of adding offsets or another sidebar mode.

The canvas now fills the main area with the existing 32px desktop gutters. Measured after the fix:

| Sidebar | Canvas left | Canvas right | Canvas width |
| --- | --- | --- | --- |
| Expanded | 272px | 1481.33px | 1209.33px |
| Icons only | 96px | 1481.33px | 1385.33px |

The right edge stays fixed while the content gains 176px. The account control also ends at x1481.33. Existing reading and form column caps remain. The dossier is unchanged. The initial synthetic receipt detail was unavailable; the later shell audit below uses a populated existing fixture.

Two updated canvas tests failed before the fix and pass afterward. They cover Home, Inbox, Transactions, Business settings and the shared header gutters. Targeted ESLint and whitespace checks pass. Screenshots are right-edge-before.png, right-edge-fixed-expanded.png and right-edge-fixed-collapsed.png in the evidence folder above. No commit, handoff or deployment.

## Search and release limits

PR1241 deliberately held Business search behind a default-off readiness flag. The intended design includes search across Business screens. NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED=true is set only on this synthetic local preview, without env-file writes. Hosted/default search remains unchanged.

The preview contains populated sample data, not a real new-user cold start. Onboarding remains a separate design discussion. Existing Transactions synthetic fixtures produce duplicate record-key warnings. Integration must verify connected search authorization, result accuracy, pagination, empty/error states and cross-Business isolation before release enablement. Keep these notes for a future approved handoff. No backend work has been requested.

## Shell verification, October 23

The approved B behavior and anchored right edge passed the local shell review. No application code changes were needed during this verification. The throwaway API now exposes the repository's existing synthetic receipt detail, original image and read marker routes so the dossier can be checked with content.

| Local browser check | Result |
| --- | --- |
| Desktop, light and dark, dossier open, both rail widths | Canvas right stays at 841.33px; dossier stays at x873.33 through x1513.33. Canvas left changes from 272px to 96px. No document horizontal overflow. |
| Desktop keyboard close | Escape while focused inside the dossier closes it and restores focus to the originating receipt row. Escape on the rail leaves the non-modal dossier alone. |
| 390px portrait, light and dark | Record opens as a full page. Header, fields and bottom navigation fit. Light-theme lower controls and original receipt are reachable by scrolling; Back returns to Inbox. |
| 320px portrait, light and dark | Record title/status wrap and fields fit the narrow viewport. Existing bottom navigation remains visible. |
| 844px by 390px landscape, light and dark | Compact rail and search remain visible. Record uses the full-page layout and vertical scrolling. |

Evidence: /Users/garces/.codex/visualizations/2026/10/22/01a164fb-0899-7500-a387-b81e8f79f1a3/home-shell-20261023/shell-lock. Desktop dossier images include light-dossier-expanded.png, light-dossier-icons.png, dark-dossier-expanded.png and dark-dossier-icons.png. Mobile and landscape captures include the temporary viewport harness for context.

Limits: responsive browser viewports, not physical phones; no new hosted, backend, screen-reader or OS reduced-motion verification. Existing 77 sidebar/layout tests plus 2 canvas tests are the implementation evidence, not a full-suite claim. The prior repository typecheck errors and synthetic Transactions duplicate-key warnings remain recorded above. Record-form polish is outside this shell check. Home still contains populated fixtures and must not be presented as cold-start onboarding.

The main throwaway preview is returned to Home. No handoff, push, commit or deployment. Next design discussion is the actual cold-start Home journey.

## Baseline lock, October 23

Lucas approved the verified shell as the expected base behavior. The canonical contract is the Shell baseline section of `.agent/designs/cuadrao-business-app/DESIGN.md`. Future Home and onboarding work must preserve it. The existing focused tests and browser evidence above protect the contract; no new application behavior was introduced for this documentation lock. No commit or handoff was requested.

## Home feedback follow-up, October 23

Founder observed that marking the Por cobrar row produces a save-failure notice above the cards and shifts their position. Screenshot supplied in the design conversation: codex-clipboard-d786aa8e-b918-4424-ae21-ca895df6a46a.png. Record this for the Home design pass only; no implementation or handoff requested.

Review a non-displacing failure notification with Reintentar, and a success notification with Deshacer for reversible payment-status changes. Compare with the existing upload notification pattern before choosing a shared treatment. A failed save must restore the previous row state, identify the affected item and remain discoverable; Retry should appear only when retrying can help. Undo belongs to a successful reversible change, not a failed save.

The current Inicio design rule explicitly uses inline failure feedback and success toasts. Changing failures to toasts is a proposed revision, not an already-locked rule. The required outcome is stable card geometry and clear recovery. Do not generalize this into replacing field validation or every error with a toast. This observation is from the synthetic preview and does not prove a hosted save failure.

## Home setup prototype, October 23

Decision under review: a collapsible Business setup section below the top bar, separate from mature Home cards. The founder excludes first upload, processing and first review from this bar; Agregar remains the upload entry point. No onboarding design is locked yet.

- [x] Scope the decision: placement, density and expanded/collapsed behavior for Business creation or invitation.
- [x] Gather references: skip new search; founder supplied and reviewed the setup reference in the conversation.
- [x] Build throwaway: `temp/home-setup/index.html`, served on local port 4397. No application source or locale edits.
- [x] Put states behind one switcher: no Business, invitation, Business ready; light/dark; desktop/mobile.
- [x] Verify the visual surface: collapse/reopen, Add before setup, simulated create and invitation paths, desktop and mobile rendering.
- [ ] Present for founder review; implementation waits for the chosen direction.

Model the Domain: one situation value drives setup content and whether it is present. Create and join are alternate situations, never consecutive checklist requirements. Mock forms, role copy and completion are synthetic interaction sketches, not wired service behavior or an approved new Business form container. The final implementation must reuse the agreed Business setup surface. There is no real upload, membership or account creation in this static mock.

Evidence is under the visualizations home-setup-study directory. No commit, push or handoff.

### Inline setup prototype revision

Founder requested the setup form inside the expanding bar, with only Business name and primary operating country required. Optional Business details remain deferred. The mock now has an inline create form and inline invitation review. Country suggests DOP, USD or CAD for reporting; explanatory copy preserves DOP/USD/EUR/CAD document currencies without conversion or aggregation. This copy is a product proposal, not proof of currency support in every backend path.

The mock uses one persisted situation, current step, open state, name and country under a mock-specific browser storage key. Name and country survive collapse and refresh. Persistence is local to this mock/browser, not server synchronization. Simulated creation and joining retire the setup bar. Verified empty-name inline error, correction, draft restoration, simulated create and join, plus the mobile dark layout. No application or backend changes, commit or handoff.

## Workspace capability map and prototype alignment, October 23

Read-only source audit used local integration 724298026c9ebadf9cc7652ed1c74a2dd24c24cf. Design application preview remains based on fe233679257035ea2dce8998b510868be9989632. No source merge, hosted call, backend test run or handoff. Interactive map: temp/home-setup/map.html, served on 4397/map.html. Setup prototype remains temp/home-setup/index.html.

The existing Business menu was inspected in the local browser: own Business, Configurar negocio, Cambiar de negocio, and a granted client with Ver y preparar. Client data and the access list fail in this preview because its synthetic API lacks those endpoints; that is not evidence of a hosted failure.

Verified current contracts:
- One owned open Business per person, plus many granted Businesses. Creation is idempotent for the owner. Current create does not establish a firm/client hierarchy or allow creating many owned clients. Sources: domain/business/spaces.py:108; api/routers/business.py:318.
- Owner read/prepare/approve; invited person read/prepare. Approval and access management stay owner-only. Export requires read. Source: domain/business/access.py:29 and export.py:456.
- Existing confirmed account receives access directly; otherwise a pending seven-day invitation. Confirmed-email reads accept matching invitations. The existing acknowledgement marks access_seen, not acceptance. Sources: api/business_spaces.py:91; api/routers/business.py:353. Email delivery is separately gated.
- Selected-client upload is supported by backend scope and has a Postgres test at tests/test_business_scope_switch_routes_postgres.py:314. Current web BusinessAddMenu.tsx:23 hides it for accountant. This corrects old own-only upload assumptions; frontend exposure needs integration review.
- Email intake supports per-Business alias/address, authorized senders, delivery history/retries. The create API requires alias while BusinessEmailDeliveries.tsx:87 calls createEmailAddress without one. Treat as a source-level mismatch to verify, not a completed end-to-end path.
- WhatsApp already has link-code verification/status/unlink UI, gated separately. Current api/whatsapp.py:543 restricts linking to the caller's own Business and refuses client grant scope. Intake uses the verified sender destination, not free text. Multi-client forwarding is a proposed extension to align, not a missing routing system overall.
- Sales-document tracking and received e-CF checks exist. Activation/issuance API was not located in the inspected source. The demo activation journey is a proposal, never proof of live issuance.

Prototype revision exposes the Business menu and own/client contexts; replaces generic team invitation with explicit access scope; replaces the synthetic accept-invitation claim with acknowledgement of received access; adds receiving channels and separate receipt-reading control; labels invoicing via external Pilot/Demo review control. All mutations are browser-local simulations. The optional phone/address fields from the prior sketch are proposed data additions, not claimed backend fields. Country-specific fiscal validation and real email alias availability are not implemented by this mock. Invoicing pilot visibility remains a design decision. The future partner intake path is outside the current prototype.

Ownership remains in the design lane. No backend assignment, orchestrator message, commit, push, handoff or deployment.

### Browser verification of capability mock

- Verified map owner/client selection and corrected table structure.
- Verified owner setup, access explanation, pilot/demo invoicing controls, and shared-Business restrictions in the local interactive mock.
- Verified mobile-width dark layout, mobile Business switcher, and switching back to owner restores owner controls. Checked light desktop visually. No browser console errors observed in the prototype.
- Corrected invitation wording to match confirmed-email access, mobile menu entry, hidden owner-only channel forms, and role-sensitive configuration labels.
- These are synthetic browser checks, not backend integration, real-device, or hosted acceptance. Full accessibility and responsive release checks remain for a later approved checkpoint.


## Notification list, local preview, October 25

Implemented the compact bell popover and shared phone sheet in the design lane.
Three synthetic notices cover an accepted invitation, receiving channels, and
profile customization. Two begin unread. Samples require development mode,
mock auth, an explicit preview prop, and a selected Business. Direct or nonmock
use stays empty. Visible copy uses the selected Business name; the sample does
not grant access or claim a real delivery.

All/Unread, mark all read, per-row dismiss, and quiet settings actions work in
memory. Read and dismiss state is keyed by Business and notice, survives closing
and switching Business, and resets when the shell unmounts. Actions open existing
Configurar tabs for equipo, correo, and datos. No storage or network calls were
added. The nested filter uses the shared overlay stack, keeps focus inside the
panel, and receives Escape before the parent. Dismiss moves focus to the filter.

Deferred backend and hosted work: define canonical recipient and Business
permissions; obtain authorized notices from the backend; persist read/dismiss
state across devices; validate each action target against current access; define
actual event and delivery timestamps. Existing settings access checks remain the
authority. This preview is not evidence of real notifications, delivery, durable
state, or hosted readiness. Backend, migrations, push, deployment, and orchestrator
handoff remain out of scope. This frontend change is a local checkpoint commit.

Verification: 21 focused notification and top-bar tests pass; scoped ESLint and
`git diff --check` pass. Browser checks covered Spanish/light and English/dark on
desktop and a 390px phone viewport, with no horizontal overflow. Verified the
custom filter, nested Escape, read-all and dismiss focus, empty unread state, and
the Recepción action. Screenshots are stored outside Git in the task visualization
folder. These are local browser checks, not physical-device or hosted acceptance.

## Notification empty states, October 25

Added a shared decorative bell to no-notifications and no-unread states. The
Model the Domain principle keeps these states derived from notice counts; there
is no separate empty-state flag. View all restores existing read notices, and
final dismissal retains focus inside the panel. No backend work or handoff.

Prove It Works verification: 26 focused notification and top-bar tests pass.
Scoped ESLint and diff whitespace checks pass. Local browser review covered
desktop and 390px phone viewports, Spanish and English, light and dark themes.
The image loaded at 88px, text remained readable, and no horizontal overflow
was observed. Verified View all, final dismissal focus, and hidden list tools
when no notices remain. Evidence screenshots are outside Git in the task
visualization folder. This is not physical-phone or hosted acceptance.

Backend acceptance remains deferred: only show these empty states after a
successful authorized response, distinguish loading/offline/failure, and preserve
recipient/Business isolation plus durable read/dismiss state across reloads and
devices. Marking all read must not remove rows from the All view.

Artwork: built-in image generation, transparent output copied unchanged to
web/public/images/notifications/quiet-bell.png. Style reference was the existing
web/public/images/auth/confirmation-envelope.png. Prompt: a single upright,
gently tilted notification bell with rounded paper/clay forms, forest-green body,
cream clapper/highlights, sage folds and a restrained lime detail; centered square
composition, readable at 88px on white and charcoal; transparent background,
no envelope, text, badge, motion lines, dramatic glow, drop shadow or background
shapes. Original generated image retained outside the repository.
