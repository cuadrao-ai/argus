# Bandeja cleared design checkpoint, 2026-10-27

## Clearance and frozen source

Lucas explicitly cleared this checkpoint: “Good, lock it and hand it off.
Checkpoint is clear.” This document supersedes earlier tentative design notes.
Design and screenshots may now be shared with Integration Orchestrator.

- Workspace: `/private/tmp/argus-reception-design-20261026`
- Branch: `codex/reception-design-20261026`
- Parent: `7bb54b472715e1fa0268de943f648e67659de14b`
- Frozen commit: the commit containing this document, titled
  `feat(bandeja): freeze approved inbox design checkpoint`.
  The exact SHA is supplied in the handoff message and external evidence manifest.
- Root owns reconciliation with newer connected integration, independent
  verification and release gates. This clearance does not authorize migrations,
  deployment, provider activation, production changes or new backend scope.

## Approved surface

Bandeja is an incoming-content workspace. Outgoing invoices and customer payment
receipts remain in Facturación. The list fills the shared canvas and retains
Cuadrao typography, colors, status pills, filters, date control and pagination.

Desktop order is Contenido, Adjunto, Canal, Remitente, Monto, Moneda, Estado,
Llegada, action. Monto and Moneda default hidden and retain that order when shown.
Remitente has a 180px minimum and 240px cap; Estado has a 240px minimum. Adjunto
is left-aligned with 104px allocation. Compact screens combine channel/sender;
phones use the readable stacked list. Review readiness is neutral; exceptions
retain the stronger treatment. No visto has a reserved dot and title weight 600;
Visto retains weight 400. Selection is a separate fact.

The toolbar uses search, arrival-date control, Filtros, Agregar split pill and
settings. Agregar uploads; the chevron exposes forwarding address/copy or setup.
Settings expose row density and optional information, not column reordering.
Filters use checkbox multiselects, draft/Aplicar, OR within groups and AND across
groups, removable chips and synchronized top views. Dates default to all dates.
Pagination uses the exact shared layout and 25/50/100 rows, including page 1 and
disabled arrows on a single page. Selecting rows changes the toolbar mode without
adding a banner; bulk archive/restore and visto/no visto use shared undo toasts.

Row inspection opens the shared AdaptivePanel dossier shell. Original file,
verbatim caption/note, channel, sender and arrival are clear and separate. The
original starts expanded. Specific Revisar/Resolver/Ver registro actions retain
existing financial dossier routes. Closing returns focus and preserves local
list position. Source retry keeps focus in the dossier. Opening marks personal
seen state only, never approval or issue resolution.

Files use captured identity or original filename. Delivery exceptions use actual
subject or sole filename, with the actual failure in Estado. A standalone note
uses opening words, WhatsApp context and Ver nota; Adjunto displays a dash.
The explicit synthetic note remains labeled preview. No caption duplicates,
automatic conversation promotion, timing-based links or new expense pipeline.

Empty states use the approved artwork. Loading rows inherit the current grid,
density, optional fields and phone layout, with shared delayed shimmer and reduced
motion. Selection is disabled during loading. The Facturación navigation glyph
uses the shared animated icon convention.

## Implementation limits

The new surface is development/mock-auth gated. Archive/restore, personal seen
state and undo are in-memory preview interactions and reset on reload. Removing
the preview banner did not establish persistence. `prepare` is a provisional UI
archive guard, not an approved server capability. Selection covers the current
page and clears on page, Business, filter and search changes.

Filters, counts and pages describe loaded arrivals, not a complete server result.
New discovered arrivals wait for explicit refresh. Dossier return state is local,
not reload persistence. Sender identity must come from authoritative phone/name
or uploader fields; never infer it from a supplier. Standalone WhatsApp note
promotion still needs an explicit supported intake contract. Existing stored
conversations do not automatically belong in Bandeja. Any future Preparar gasto
must reuse the existing draft/review pipeline and must not treat text as payment
proof or financial approval.

The local email fixture lacks the message-detail endpoint. Its unavailable/retry
state is retained; successful original-message rendering was tested with an
explicit synthetic local response. Connected acceptance remains required.

## Existing archive and seen code inspected

- `web/components/chat/useArchiveActiveConversation.ts`: desired archive boolean,
  duplicate-flight guard and success/error handling are useful patterns.
- `web/components/settings/ArchivedChatsView.tsx`: separate archived list and
  restoration without deletion are reusable interaction concepts.
- `src/argus/api/routers/conversations.py` and
  `src/argus/domain/supabase_gateway.py`: conversation archive is user-owned,
  with different permissions and scope. Its generic patch also accepts deletion
  fields. Do not reuse that endpoint or payload for shared Business arrivals.
- `src/argus/api/business_receipt_activity.py`: personal completion-cursor
  acknowledgment exists for ready receipt extraction. It is not a general
  seen/unseen API for failed receipts, emails or typed captures.
- `web/components/business-app/ReceiptSeenBoundary.tsx`: existing visible/focused
  acknowledgment remains intact. It must not become financial resolution.

No compatible arrival archive/restore endpoint was found in this baseline.
Financial-account archives and export archives are unrelated. Reuse the narrow
patterns above only; do not move or hide financial records or original evidence.

## Required backend checkpoint

1. Durable Business-wide archive/restore of an arrival only, with canonical
   identity across receipt/email/capture kinds. Restore cannot duplicate an entry.
2. Server-enforced editing capability, actor attribution, Business isolation,
   row-level security and refusal after permission revocation.
3. Durable personal seen/unseen for each arrival kind. Opening detail affects
   only that person's attention state, never extraction, approval or payment.
4. Idempotent desired-state requests and safe retries. Version/conflict behavior
   must be explicit; repeated requests must not duplicate Activity events.
5. Shared Activity events for archive/restore with actor, time, Business and
   arrival. Shared audit history is never archivable through inbox actions.
6. Originals, linked drafts/records, issues, approvals and payment state remain
   unchanged. Archived unresolved issues still count in Home/Registros attention.
7. Bulk per-item outcomes, partial failure display, failed-only retry and retained
   failed selection. Never report blanket success after partial failure.
8. Reload and second-session persistence proof; shared archive visibility across
   authorized teammates; personal seen isolation between users. Verify with a
   disposable database and synthetic data before claiming backend readiness.
9. Server query contract for arrival date, multiselect channels/sender IDs/states,
   filtered total, stable page/snapshot ordering and new-arrival discovery.
   OR within groups, AND across groups. Selected sender identities survive search.
10. Actual sender identities: current baseline supplies email sender text but not
    manual uploader identity or WhatsApp sender phone. Do not infer sender from
    merchant. Supply normalized IDs plus available display name/address/phone.

No automatic retention, auto-archive, deletion, financial bulk approval or bulk
retry of extraction is in this scope.


## Seen-state and undo concurrency

Use authenticated user + Business + stable arrival identity. Set desired states
idempotently, never toggle blindly. New arrivals are unseen per user; define
backfill explicitly. A late request must not overwrite a newer explicit unseen
action. Undo restores each successful item's prior field value only, with current
permission/version checks. Retain failed selections and retry only failures.
Never reverse unrelated changes or carry actions across Business scope.

## Changed-file ownership and integration instructions

- Owned implementation: `web/components/business-app/recepcion/**`, including
  original artwork, plus the BusinessInboxPanel adapter and five Reception tests.
- Shared alignment: BusinessPanel canvas assignment, BusinessWorkspace heading,
  and two matching existing DOM assertions. Preserve connected behavior.
- Navigation: BusinessSidebarNav, nav-glyphs.tsx and nav-glyphs.module.css contain
  the requested animated Facturación glyph only.
- ReceiptSourcePreview: optional initialExpanded=false and
  showArrivalContext=true. The owned dossier opts into expanded source and hides
  duplicate channel/time only. Email/download/repeat-delivery links remain.
- RecordsPagePreview delegates its existing footer to RecordsPaginationControls;
  RecordsDatePreview accepts optional arrival/all-dates labels;
  RecordsFiltersPreview delegates its checkbox block to RecordsFilterSelection.
  Shared defaults and CSS remain unchanged. These named leases are returned.
- Paired locale additions stay inside business.reception_preview. DESIGN.md has
  Reception-only guidance. The report retains iteration history, not authority.

Apply minimal shared diffs to current integration. Do not copy old shared files
wholesale, overwrite newer connected query/page callbacks, or enable preview
organization as if it were durable. Root owns conflict resolution. The exact
changed-file inventory is available via git diff of the parent and frozen commit.

## Verification and evidence

Targeted Reception tests and lint pass; detailed results are in the external
checkpoint manifest. Local headless checks cover receipt/note/email dossiers,
existing review routing, full original text, error/retry, focus return, English
header spacing, responsive grids and reduced-motion loading at 1920/1440/390px.
Desktop skeleton grid and row height match actual rows; phone height adapts to
metadata. No page overflow or JavaScript errors occurred in these checks.

Whole-project typecheck has existing broad test/type diagnostics; this is not a
green full-project build or integrated acceptance. No hosted/provider/model calls
were made. Preserve earlier completed evidence and run the focused matrix again
on the integrated candidate; no backend readiness is inferred from preview tests.

The external evidence bundle contains selected screenshots, browser scripts,
check outputs, source/file inventory and SHA256 hashes. It is outside Git; no
visual evidence is committed. Its absolute location is in the handoff message.
