# Cuadrao native design: approved interaction decisions

Status: historical founder-approved study, locked September 30, 2026.
Current native rules live in [Cuadrao DESIGN.md](../../.agent/designs/cuadrao/DESIGN.md).
Its later shared gestures and Home shortcuts supersede the hold-menu, header ellipsis
and reorder-tray entries below. This study preserves provenance, not current delivery status.
Applies to the Cuadrao native design canvas. This is not a financial API contract,
a shipped-capability claim, or authorization to replace the connected client.

The founder approved preserving the previous evening's Accounts work as a whole,
then carrying it into native UI. The source is the reviewed local HTML account
study plus the explicit conversation decisions. References inform presentation;
they do not reopen these decisions.

## Current design checkpoint — September 30, 2026

The founder requested locking the work so far, identifying remaining design work,
and prioritizing a usable physical-iPhone experience. This section is the current
summary; dated sections below retain decision history and supporting evidence.
Locked means preserve the reviewed baseline, not final polish or connected delivery.

| Surface | Preserve now | Still to design or verify |
| --- | --- | --- |
| Welcome and account access | Welcome composition, provisional mark/pine palette, Tus finanzas, en orden; create account, sign-in and recovery UI | Real auth states and handoff, device language selection, complete English parity, physical keyboard/accessibility review |
| Home and navigation | Personal / Hogar / + selector; all active accounts; Movimientos distinct from Próximamente; Ordenar Inicio; icon-only navigation with approved Home, calendar, profile and bell artwork, including Novedades | Panorama meaning and useful content, realistic long/unknown/error/loading states, navigation motion and physical-device polish |
| Accounts | Add/type/name/optional balance, currency entry, details, actions, reorder, archive/restore | Present the existing connected transaction inspection/correction, transfer/refund and reconciliation capabilities coherently; richer account/asset details; loading/failure/recovery presentation |
| Household | Empty Home, create/open Hogar, native share-link preview, recipient accept/defer, Personas owns invitation/member status | Auth/install handoff, invitation expiry/revocation recovery, explicit sharing and visibility/editing explanations, leave/remove consequences under approved production contracts |
| Plan | Calendar navigation icon | Cuadrao overview and detail presentation for budgets, savings goals, debt plans and commitments, using the delivery lane's existing capabilities |
| Search | Navigation entry | Cuadrao search/results/detail presentation and empty/error states |
| Assistant, Profile and Novedades | Placement; profile and bell artwork | Actual Cuadrao destination screens, minimum account/settings controls, assistant entry and result presentation, meaningful updates |
| Shared visual system | Native SwiftUI, Spanish-first review, reusable components and vector assets, light mode | Final logo/brand decisions, consolidated typography/spacing, accessibility, language coverage and device verification; dark mode remains deferred |

### What separates this canvas from daily phone use

At design source `da2012f5a25f66b04828a2b37712a15b1b96c4c1`,
`ArgusFoundationApp` selects `CuadraoCanvas` with `--cuadrao-design` and otherwise
launches the connected `FoundationShell`. The design canvas is native code, but
its accounts and household state are sample state. Apart from saved Home order,
that preview is not durable financial storage. Other menu destinations remain
placeholders. The welcome canvas currently pins Spanish: having English strings
in source is not verified runtime localization parity.

Two separate milestones prevent misleading completion claims:

1. **Review on the phone:** install the existing design preview in a distinct app
   identity, preserving the connected app/session. Verify navigation, keyboard,
   safe areas and text at actual device size. This can precede the rest of the
   design; sample data remains explicit. Current simulator proof does not prove
   physical-device signing/install, launch from the app icon, or internet access.
2. **Use with real records:** adapt the approved screens to existing session,
   account and financial-operation owners. Start with sign in, Home, accounts,
   record/inspect/correct and reopen, including failure/recovery and minimum
   profile/sign-out controls. Preserve capabilities and canonical money rules;
   do not create a parallel ledger or treat sample acceptance as real membership.
   Real phone-over-internet delivery remains coordinated with the delivery lane.

### Recommended priority, not a new implementation assignment

- **Next local step:** physical-phone design preview and the focused reuse map
  below. Use the current simulator/build cache for local checks; no new demo farm.
- **Next design surface:** Plan as a complete overview-to-detail experience,
  informed by the approved account controls and existing financial contracts.
  Apply the established Mobbin/Apple reference exercise before design changes.
- **Connection priority:** the personal account loop above, then Plan and Search.
  Carry minimum account/settings and recovery UI with that usable loop instead
  of waiting for a fully redesigned Profile. Existing assistant capabilities are
  preserved; missing Cuadrao styling does not retire them.
- **Subsequent design:** remaining household sharing/management, assistant,
  Novedades and broader Profile. Final brand, dark mode and decorative motion do
  not block a useful phone review.

### Parallel VM candidate: connected-UI reuse map

Proposed bounded read-only assignment, not dispatched by this checkpoint. Compare
this exact design checkpoint with a freshly recorded integration SHA; account for
active delivery changes separately. The delivery chat was inspected during this
checkpoint and is actively finishing personal assets (PR #759), so that work is
not available for a competing implementation assignment.

Deliver one actionable matrix: Cuadrao screen/action -> existing native
model/session/API owner -> required presentation adapter -> unresolved product
choice, if any. Cover authentication, Home, accounts/activity/reconciliation,
Plan and Search. Include existing test/evidence pointers, language/accessibility
omissions, and the smallest safe connection sequence. Identify duplicated state
that must be replaced by canonical owners; do not suggest synchronizing two ledgers.

A Linux VM can inspect code and prepare this handoff. It cannot supply the local
Xcode/signing/physical-iPhone acceptance evidence. No changes to SwiftUI, financial
runtime, contracts, prompts, migrations, hosted settings, demo processes or
simulators; no paid calls, push, merge or deployment. Keep the report in the VM's
own workspace for review. Refresh references before any later implementation.

## Locked

| Surface | Decision |
| --- | --- |
| Home | Accounts live in the feed. Show every non-archived account; no View all / Show less, cap or internal scrolling. The section pushes later content down. |
| Accounts heading | Text only. Add (+) and section options (…) on the right. |
| Tap | Open the account's balance and activity. |
| Hold | Open account actions: rename, add transaction, archive. Icons on the left. No move-to-space or delete action. |
| Section options | Reorder accounts and Archived accounts, with leading icons. No archived counter. |
| Reorder | Explicit mode entered through section options. Show drag handles in the Home section and Done. Holding a normal row continues to mean account actions. |
| Archive | Hide the row while preserving its data/history. Offer Undo; archived accounts can be restored. |
| Account detail | Native back navigation; one consistent (…) action entry. No separate pencil or duplicate management heading. Balance and activity lead; one obvious add-transaction action. |
| Add account | Cash, Checking, Savings, Investment, Credit card, Loan. Other assets expands Property, Vehicle and Other asset. Original approved vector icons. |
| Required fields | Type required. Name optional, falling back to type; balance optional and blank means unknown, not zero. |
| Amount | Currency code and picker inside the left edge, number right aligned. No repeated symbol/code or formatted readback. Plain native field background. |
| Typing | Latest reviewed HTML uses whole-number entry, optional decimal cents, live comma grouping, padding on blur. This supersedes the earlier cents-first experiment. Keep selection/caret; reject letters, excess precision and amounts above 9,999,999.99. Never silently round pasted amounts. |
| Input tone/motion | Empty 0.00 is gray; positive entry uses a legible teal. Grouping motion must not delay the actual entered value. Respect Reduce Motion. |
| Add action | Disabled while the type is missing or input needs correction. A contextual info lip slides above the action and collapses when valid. |
| Copy | Name; Loan; Other assets. Remove fictional-information footer, Private to you, and leave-blank helper. Optional labels remain. |
| Navigation | Home, Plan/calendar, assistant, Search, Profile. No visible icon labels. No Accounts tab. Exact approved Home icon; assistant mark remains provisional. Bell at upper right. |

## Still open or preserved elsewhere

- Home structure is locked as summarized above. Panorama content, final branding,
  typography/spacing polish, assistant mark and navigation-bar motion remain open.
- Swipe actions are deferred. Native does not inherit the green web swipe control.
- Balance-check semantics and detailed reconciliation remain owned by the existing
  connected financial experience. Do not redesign them as part of this pass.
- Account-detail monthly summaries, richer editing metadata, transaction types,
  inspection/correction and advanced asset details retain their existing product
  contracts. Their absence from a visual canvas is not a product-scope deletion.
- The current entry/review preview stages sample rows only; it does not implement
  ledger effects, reconcile balances, persist data, or call the API.

## Reference exercise

Inspected inline Mobbin screens on September 30, 2026:

- [Wise balances](https://mobbin.com/flows/469559a0-00d1-468e-abf8-6400019d6f3d):
  clear account identity/balance, actions, then transaction history.
- [Reminders reordering](https://mobbin.com/flows/cd8cc37e-987f-48fe-ae62-bbc38931471e):
  explicit edit mode, row handles and a completion control. Search requested
  Things; returned reference was Reminders and is identified accurately here.

These are captured flows, not claims about the latest installed app version or
animation timings. Apple [sheets](https://developer.apple.com/design/human-interface-guidelines/sheets)
keep a scoped task close to its context; [context-menu guidance](https://developer.apple.com/design/human-interface-guidelines/context-menus)
keeps object-specific actions out of the main layout. The founder's leading-icon
sheet choice is preserved using native presentation rather than web dialogs.

Implementation/evidence: [Accounts evidence](../reports/evidence/cuadrao-native-design/accounts/README.md).

## Home spaces continuation — September 30, 2026

Founder explicitly retained the original quiet horizontal selector: Personal /
Household / +, with additional named spaces in the same row. Spaces change Home's
context; they are not stacked account groups or new menu-bar destinations. This
restores the existing MVEE/DESIGN direction within the Cuadrao native canvas.
The existing account interactions apply within the selected context.

[Native implementation and evidence](../reports/evidence/cuadrao-native-design/spaces/README.md)
records the scoped sample-data behavior, design references and remaining limits.
Household authorization and financial contracts are not implemented by this work.

## Home feed language — September 30, 2026

Founder-approved after reviewing the feed labels:

- **Movimientos** (English: **Activity**) labels recorded money changes: spending,
  income, transfers, payments, refunds and adjustments. Do not rename this money
  list to Transacciones or Actividades.
- **Próximamente** (English: **Coming up**) labels upcoming commitments and expected
  items. Keep these separate from recorded movements; intentions are not actuals.
- **Actividad** is suitable for a future mixed event feed, if separately designed;
  this decision does not create that feed or add invitations/app updates to Movimientos.
- This locks the labels and content distinction, not the remaining Home layout,
  section order or financial implementation.

Reference: [Wise's Transactions list](https://mobbin.com/screens/47d57013-eb4e-4b53-bda0-f1d83c5dd280)
contains money entries; [Monzo's All activity feed](https://mobbin.com/screens/8f921563-4da7-4e2b-98ea-e3e5e47b9229)
includes payments and nonfinancial events. The inspected captures were English;
the Spanish labels are Cuadrao's own approved wording, not attributed translations.

## Home customization — September 30, 2026

Founder approved Ordenar Inicio → drag whole sections → Listo. Panorama,
Próximamente, Cuentas and Movimientos can be reordered; logo, space selector and
menu bar remain fixed. The starting order is a default, not a user restriction.
Account long press continues to open account actions.

The native canvas provides an explicit compact reorder sheet from Home's footer,
with Cancel, Done and Reset. A saved local order applies across spaces and survives
relaunch. Empty sections retain their place without adding empty feed content.
[Implementation evidence](../reports/evidence/cuadrao-native-design/home-layout/README.md).
This is a presentation preference, not a new financial backend flow.

Label refinement: **Ordenar Inicio** / **Reorder Home** replaces Personalizar Inicio /
Customize Home. This control changes section order only.

## Earlier Home checkpoint — before first-use and invitation work

Founder requested preserving the current structure and explicitly tracking what
remains. Home is structurally settled for continued design work, not visually
final or complete across all first-use and household states.

**Preserve:** space selector; account section and approved account interactions;
Movimientos versus Próximamente; reorderable sections with Ordenar Inicio; fixed
brand/space/navigation controls. Revisit these only through an explicit design
change, rather than reopening them during routine polish.

**Remaining Home detail work:** headline Panorama meaning and presentation;
final typography, spacing and visual rhythm; menu-bar motion; realistic and
long content; larger text, VoiceOver and physical-device review. Final brand
identity and dark mode remain app-wide decisions.

**Historical coverage before the continuations below; see the current checkpoint
above for present status:**

| State or flow | Current design state | Remaining design work |
| --- | --- | --- |
| Personal Home with no accounts | Existing first-account invitation and native add form | Review first use through first recorded/unknown balance; missing versus zero; no premature empty feed sections |
| Household Home with sample records | Shared-context header and joint-account examples | Complete meaningful shared summary/commitments; verify real-looking content and incomplete information states |
| Household with no shared records | Reuses the generic first-account card | Design a purpose-specific empty state; distinguish no household, invitation pending, and joined but nothing shared |
| Household creation and invitations | Add opens only an empty local context | Design create/invite, recipient acceptance, pending/expired/revoked invitation and recovery screens |
| Explicit sharing | Not designed in this native pass | Choose an existing account or add a joint record; preview who sees what and editing rights; review/revoke sharing |
| Household management | Not designed in this native pass | Members, invitation management, leave/remove and resulting access/history explanations, respecting unresolved production policies |

The MVEE household section remains the owner of existing consent and privacy
boundaries: joining alone does not share private records or create a joint
account. This checkpoint does not approve a new permission model, invitation
integration, financial rule or backend implementation. Household flow proposals
still require the usual design-reference and founder review exercise.

## First-use design baseline — September 30, 2026

Implemented for founder review in the native sample canvas after the Mobbin pass:
Personal with no accounts; Household creation introduction; Household alone;
invitation pending; joined with nothing shared. Empty Personal has one add-account
entry point; empty charts, summary totals and reordering are deferred until content
exists. The existing section order and populated account interactions are retained.
Household pending/joined states do not create or share private account records.

[First-use evidence and preview instructions](../reports/evidence/cuadrao-native-design/cold-start/README.md)
record the native journey and its limits. This advances the earlier checkpoint's
first-use/empty-household rows; it does not close the complete invitation, sharing
or member-management design. The later invitation-link continuation supplies the
recipient preview; the production invitation mechanism remains open. Preview-only
simulation is labelled explicitly.

## Household invitation-link baseline — September 30, 2026

Founder approved replacing the name-entry mock with a native share-sheet link and
recipient acceptance preview. Compartir invitación lets the system offer installed
sharing destinations; no contact permission or custom WhatsApp integration is
required by this design. Creating/copying/sharing a link is distinct from delivery
and membership: closing the sheet never asserts either. The recipient can accept
or choose Ahora no, with private accounts preserved.

[Current invitation preview and evidence](../reports/evidence/cuadrao-native-design/invitation-link/README.md)
supersedes the earlier pending-name and Simular aceptación controls. Spanish is
primary, with English copy alongside it. Links are nonfunctional examples and
acceptance affects only in-memory sample state. Auth/install handoff, real invite
rules and shared-account permissions remain open production contracts.

## Household concern separation — September 30, 2026

Founder approved: Home owns the shared financial picture; **Personas / People**
owns membership and invitation status. Remove Home's prominent pending-link card
and status-dependent hero wording. Empty Hogar consistently emphasizes adding a
joint account, with a quiet invitation shortcut before a link exists and Personas
afterward. Populated Household also uses Personas. No invitation reminders,
badges or delivery tracking are introduced.

[Native visual check](../reports/evidence/cuadrao-native-design/household-people/README.md).
This supersedes the invitation-status card in earlier first-use screenshots;
existing invitation and acceptance behavior stays within the local design mock.

## Plan navigation icon — September 30, 2026

Founder replaced the target icon with the supplied rounded calendar outline.
The native tab uses a scalable vector redraw; other navigation icons and the
icon-only layout remain unchanged. [Visual check](../reports/evidence/cuadrao-native-design/plan-calendar/README.md).

## Profile and notifications icons — September 30, 2026

Founder-supplied rounded outline references replace the default person and bell
artwork in navigation. Template vector redraws preserve the current placement,
colors and interactions. [Visual check](../reports/evidence/cuadrao-native-design/navigation-icons/README.md).
