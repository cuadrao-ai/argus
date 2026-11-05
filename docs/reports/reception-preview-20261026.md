# Bandeja design brief

Status: design checkpoint cleared by Lucas on 2026-10-27 and frozen for handoff.
This report is chronological iteration history; later entries supersede earlier
ones. The consolidated reception-design-checkpoint-20261026.md handoff owns the
final design and limits. Clearance is not hosted acceptance.

## Direction approved on 26 October 2026

Keep the name Bandeja. Use the third supplied reference as the primary composition
reference, with Cuadrao typography, colors and components. The working list fills
the canvas. Quiet dividers, consistent rows and useful actions establish hierarchy.
Do not add overview cards automatically or preserve the old enclosed-card layout.

Separate document identity, source, processing state, arrival time and next action.
Extracted money is secondary. Use the existing dossier. Preserve hover, focus,
keyboard access, selected rows and a readable phone layout. References guide the
composition, not new business rules or backend promises.

Bandeja receives incoming documents, including supplier invoices and payment
evidence. Outgoing invoices and payment receipts sent to customers belong in
Facturación and remain linked to their invoice. A unified delivery log is outside
this pilot.

## Proposed views and truth boundaries

Todos includes successful arrivals as well as unfinished ones. En proceso follows
server-reported reading state. Necesitan atención follows server-reported problems.
Keep Por revisar as a separate view for documents ready for a person to review;
it must not disappear between processing and problems. Opening a document does
not resolve it. Successful extraction does not approve its financial record.

Use authoritative counts where the existing contract supplies them. Do not infer
an all-time total from the rows loaded into the browser. Search and source filters
in this design iteration apply to the loaded list. Full-history query, pagination
and counts need a connected contract before claiming complete history.

Ver registro requires an existing linked record ID. Resolver opens an actionable
problem in the existing dossier; it does not resolve anything by itself. A
read-only caller receives a detail action. Keep email retries in their existing
detail workflow. No new issuing, payment, ingestion or delivery behavior is added.

## Current foundation

The desktop title and outer canvas now align with Registros and Facturación.
The phone title and Agregar share a row. Shared changes were supplied under a
named patch lease. This is local design work, not an integrated release.

Iterate with focused checks of changed behavior and desktop/phone rendering.
Keep screenshots and tentative feedback private until Lucas clears a checkpoint.

## Local implementation and focused proof

The development + mock-auth preview now uses a full-canvas list with four views,
loaded-list search, a source picker and separate identity/source/state/arrival/action
columns. Phone rows use a readable stacked layout. The existing dossier, upload
flow and server counts are reused. Successful arrivals remain in Todos. The normal
non-preview inbox path keeps its existing behavior and the approved alignment.

Facturación uses the existing animated navigation component with a Phosphor
file glyph. Only the invoicing import/glyph and its 240ms motion rule changed under
a named shared-file lease. Reduced motion uses the existing suppression rule.

Focused checks: 38 existing canvas/inbox tests and 4 new arrival-model tests pass.
Targeted lint and git diff --check pass. Headless synthetic browser checks at
1440px and 390px pass for views, arrow-key navigation, loaded-list search, source
filtering, upload open/close and receipt open/return. Desktop dossier closure returns
focus to its row. No horizontal overflow or page exceptions were observed. Light
and dark screenshots are retained outside committed source in local temp evidence.
The sidebar animation was observed on hover; reduced-motion computed animation
names and transforms are none. No financial mutation was exercised.

A broad TypeScript diagnostic run is not clean because this checkout has existing
Bun test declaration errors; it reported no diagnostics in the new Reception files
or BusinessInboxPanel. No full build, CI or hosted acceptance is claimed. The local
fixture still lacks the existing name-prompt and receipt-reading endpoints. The
current source contract does not establish complete historical note pagination.

## Row and toolbar iteration

Rows now use the shared status pill and density constants, with 14px primary type,
secondary amounts, and a 56px default desktop row. The document's second line names
an attention reason when there is one. Sender and channel have a separate column.
The right action is a quiet outlined control and still opens the existing record
or dossier. Selection checkboxes are independent of opening a document. Search is
right-aligned; Filtrar and the reused view-options popover control source, metadata
visibility and row height. Agregar, export and forwarding-address copy remain in
the quiet overflow menu. There is no prominent upload primary in this workspace.

### Archive decision from the user

Archiving is Business-wide organization of an arrival, not a financial operation.
Preserve the original, linked record, review/approval state and payment state.
Provide Archivados and Restaurar; keep unresolved items in Home/Registros attention
counts. Require an appropriate editing role and record archive/restore actor and
time in Activity. The shared audit history itself is not archivable. No deletion,
auto-archive or retention settings. The exact editing capability needs the backend
contract. If persistence is unavailable, defer the pilot feature; never simulate
archive by hiding rows in local state or storage.

Recovered existing code: web/components/settings/ArchivedChatsView.tsx and
web/components/chat/useArchiveActiveConversation.ts use conversation-specific
PATCH /conversations/{id}. Their restore/search patterns can inform a later UI,
but conversation archive is not an inbox-entry contract. Current lane baseline has
no matching receipt/email/note arrival archive endpoint. Archive and restore remain
deferred pending persistent support. No local archive simulation was added.

Final tag correction: use Registros' actual workflow-tag CSS and palette directly,
not the older foundation status pill. Tags are fully rounded and text-only, with
the same typography/padding and light/dark colors. Review/attention use the review
tone, reading the pending tone, and confirmed receipts the green tone. Labels still
derive from arrival state; no Record preview metadata is copied onto an arrival.

Focused row interaction checks pass at 1440px, 1200px and 390px: select-all/mixed
selection, source filter, metadata visibility, density/reset, overflow upload,
receipt open/return, focus restoration and arrow-key views. No page exceptions or
horizontal overflow observed. The integration owner independently confirmed no
persistent arrival archive/restore API or active implementing owner at aa5a2d42.
Conversation, customer, account archive and receipt dismissal must not substitute.

Table-settings correction: Bandeja reuses the Registros trigger/popover, 440px
panel width, segmented Columnas/Altura de filas controls, required-field styling,
choice rows and reset footer. Visibility and density remain local presentation
preferences. No inactive reorder handles are shown; column reordering is not added
in this bounded iteration.

Empty-state artwork: replaced the generic line icon with a new transparent inbox
tray illustration derived from the existing invoice/calendar art direction. It
uses soft rounded 3D forms in forest green, cream, sage and lime, with no financial
approval or payment symbol. The raster is owned inside recepcion/assets and loaded
through next/image. It is decorative (empty alt), static, and now 144px wide in
both empty states, matching the main Facturación illustration width. Existing
empty copy and clear-filters action remain unchanged.

Filter convention correction: search now precedes Filtros in the list toolbar.
The filter uses the existing Registros trigger, 660px panel, category rail, radio
choices and Limpiar filtros / Aplicar footer. Origen filters existing channels;
Estado selects the existing Bandeja view and stays synchronized with its tabs.
Edits remain a draft until Aplicar; dismissing discards them. Phone uses the same
full-screen sheet and group/back navigation as Registros. No new financial states
or backend options are introduced.

Focused local synthetic browser checks passed at 1440px and 390px: search order,
draft cancellation, apply, combined source/view filtering, staged clear, keyboard
rail navigation and focus return, image decoding/144px width, and no page errors
or horizontal overflow. Facturación's main artwork measured 144px wide in the same
preview. Targeted lint and diff whitespace checks passed.

Intake action correction: restored the split Agregar pill at the toolbar's far
right, after table settings. Its primary action opens the existing document intake;
the chevron shows only email intake. The three-dot overflow and export action were
removed from this private surface. The menu displays the selected Business source's
receiving address and copies that exact value, then confirms Dirección copiada.
A missing address leads to Negocio / Recepción; loading and failed address reads
remain distinct. Clipboard failure stays inline with the address available for
manual selection. The address load is scoped to source/revision and the control
remounts when the selected Business changes. Existing accountant restrictions remain.

Focused synthetic browser checks covered desktop and phone upload, toolbar order,
visible address and exact clipboard value, confirmation and focus return, missing
address setup navigation, failed address retrieval, and clipboard rejection. No
horizontal overflow or page exceptions were observed. Targeted lint passed. The
setup error-path selector was adjusted to include its existing Reintentar button;
no shared setup code was changed.

Pilot scan cleanup: kept Documento → Remitente/origen → Estado → Llegada → action,
with amount/currency beneath identity. Removed row/select-all checkboxes and all
selection state because persistent bulk archive/restore is deferred. Table settings
now says Información visible; optional source, arrival and amount remain toggles,
with document/state/action required and density unchanged. No reordering was added.
Headers use medium weight and the subtle divider; hover/focus and the open dossier
row keep restrained treatments. Agregar now precedes table settings on the right.

Seen-state finding: business_receipt_read_states persists completed receipt-read
acknowledgments per person, but the contract is not a general seen flag for every
arrival. saved_unread has no completion cursor, failed reads do not support that
acknowledgment, and notes/standalone emails have no equivalent in this contract.
Removed unseen indicators from this pilot list instead of presenting extraction
activity as universal human attention state. Existing dossier acknowledgment is
unchanged. Email sender identity stays visible where supplied; receipt summaries
do not expose message sender identity, so no name or phone is inferred.

Channel/sender refinement: wide layouts now show separate Canal and Remitente
columns. Canal is narrow; the sender keeps flexible address/name space. At content
widths of 1050px or less, they combine into sender/channel lines, including compact
row density. The visibility toggle is Canal y remitente. Channel labels and the
channel filter now use WhatsApp, Correo and Carga manual (notes retain Nota).
Missing sender identity is an accessible Remitente no disponible placeholder,
never the receipt merchant. No backend identity is synthesized.

Focused synthetic browser checks passed at 1440px, 1200px and 390px: separate versus
stacked geometry, channel wording, missing sender label, visibility/density/reset,
unchanged state after dossier open/return, and no horizontal overflow or page errors.
Targeted lint, locale JSON parsing and diff whitespace checks passed.

## Current iteration: multiselect, organization, arrival dates and numbered pages

This section supersedes earlier checkbox, source-toggle and seen-state decisions.
Canal and Remitente now have separate settings and checkbox filter groups. Sender
selection uses known identities, keeps selected options visible during search,
and never interprets search text or merchant names as sender identities. States
share one filter with the top views; multiple states highlight Vista combinada.
Draft/apply/discard, removable chips and OR-within/AND-between groups are in place.
Typed captures use Escrito aquí because they are a supported direct intake path.

At the user's request, checkboxes and local archive/restore/seen interactions
returned. The mock disclaimer was removed from the product surface. This remains
in-memory behavior, not durable backend proof. Technical boundaries and the
existing archive reuse assessment are in the technical handoff document.

Selection changes the toolbar's mode, never the table's position. Wide canvases
place compact actions beside Filtros; smaller canvases replace normal controls
in their existing space. Clear uses an accessible ×. Search does not shrink;
buttons keep icons and labels together. No colored selection banner is added.
Measured list top position was identical before/after selection at 1920, 1440,
1000, 768 and 390 viewport widths.

Arrival date uses the existing calendar, with all dates as default. Pagination
uses the extracted Registros footer and its exact CSS, including the named
container needed for the same phone layout. It supports 25/50/100, current-page
selection, reset on search/filter/date changes and count-only navigation when
there is one page. New discovered arrivals wait for Actualizar lista. The phone
return path was fixed to restore page/filter/order after opening a dossier.

Narrow rows now follow Registros' compact-list principle: one bordered list,
15px document titles, secondary amounts, grouped sender/channel/arrival, status
and an explicit row action. Empty sender dashes and desktop document icons are
omitted visually on phone. Desktop remains the stable column sequence.

Synthetic browser evidence: date-pagination-check.cjs passed at 1440/390 with
36 arrivals; toolbar-check.cjs verified unchanged selection geometry at five
widths. Seventeen pure tests and targeted lint passed. Screenshots stay private
in ignored temp/reception-startup. No hosted/provider/model requests, migration
or deployment occurred. Backend persistence and complete server totals remain
unverified and require the separately authorized checkpoint.

Monto and Moneda now have separate desktop columns and independent visibility
controls. Number formatting, adaptive amount width, 80px currency width and the
currency symbol come from Registros' existing helpers. Amount is right-aligned
with tabular digits; currency is left-aligned and muted. Unknown values use the
shared accessible dash, never zero. Phone keeps the amount and currency together
under the document. The compact list begins before the added desktop columns
would become cramped. Local checks passed at 1920/1440/1200/1000/390, including
independent toggles, missing amounts and no page errors or horizontal overflow.

Filter checkbox behavior is now one shared implementation with Registros Revisión:
RecordsFilterSelection owns the parent mixed/all/none state, label clicks, keyboard
activation, select-all/results and matching-only bulk changes. Optional sender
presentation keeps selected nonmatches visible without including them in the
search-results bulk operation. Fourteen existing/new DOM regressions and focused
1440/390 browser checks passed. The narrow shared helper lease was returned frozen.

Bulk archive/restore and seen/unseen now use the existing success toast presenter
with Deshacer. Undo restores previous membership for the affected IDs and only
the changed organization field, preserving mixed prior seen state and unrelated
changes. Toasts replace one another, use the shared action duration and focus/hover
pause behavior, and dismiss on workspace unmount so a stale action cannot target
another Business. No layout banner or new toast component was added. A focused
pure regression proves mixed-state restoration and all four reversible actions.
These are still local interactions; durable undo needs the backend contract below.

Toast browser checks passed at 1440/390 for all four actions and Deshacer,
including mixed seen/unseen restoration, one toast at a time, correct desktop/
phone placement and unchanged table position. Focus now uses preventScroll so
confirmation/undo does not jump the phone list. Targeted lint, locale JSON parsing
and whitespace checks passed.

Column spacing now follows Registros' 12px horizontal cell padding, replacing
variable grid gaps. Documento reserves the Registros text-column width plus its
32px icon slot; Remitente reserves 240px, and both share remaining space. Monto
keeps the shared adaptive width, Moneda keeps 80px, and Llegada reuses the date
column width. Protected minimum widths scroll within the table for unusually
long values; narrow surfaces retain the compact list. Measured amount/currency
text separation is 24px at 1440/1920, with 104px/80px normal column widths.
Local browser checks passed at 1920/1440/1200/1000/390 with no page overflow.

Document identity and original-file access: Documento now shows one supported
merchant/title or the original filename when unidentified/unreadable. It does not
borrow the email subject or infer a document type. Adjunto opens the existing
source preview with filename, download and arrival context. Monto and Moneda
remain separate after Remitente, using the existing money formatting and widths.
On phones the original control shares the title row and money stays secondary.
Specific failure text appears with Estado. Intake exceptions retain their own
detail route and do not show a fabricated attachment.

Contract inspection: email_intake/service.py keeps the original email as context
and captures each attachment with its own document_id; receipt rows exclude
email_original, and pending/no-receipt delivery entries remain exceptions. The
frontend neither splits pages nor groups separate files. Confirm server dedup and
explicit document relationships before any future grouping. Receipt document_type
is not a supplier-invoice classifier, so no invented invoice label is added.
Phone/uploader sender identity still needs its existing backend dependency.

Focused verification: seven model/source-preview tests pass, plus desktop/phone
checks for retained money order, single identity, original-file dialog and focus
return. ReceiptSourcePreview adds only initialExpanded=false by default; the
owned file dialog opts in, preserving existing dossier behavior. No backend or
financial state changes are introduced. This remains a private, uncleared design
iteration.

Pagination visual correction: Bandeja now uses the shared footer default, including
page 1 and disabled navigation arrows when only one page exists. This supersedes
the earlier single-page hiding request and restores the three-part Registros
layout: count left, page-size picker in the middle, navigation right. No shared
component or CSS changes.

## Standalone text-note preview, 2026-10-27

First-column copy is Contenido; Adjunto and the existing Monto/Moneda order stay.
One explicit synthetic WhatsApp note demonstrates opening words plus message icon,
sender, arrival, Sin archivo, neutral Nota recibida and Ver nota. Full original
text stays in a shared-pattern modal/sheet. Row and detail explicitly say preview;
no amount is extracted from the text and no Preparar gasto button is offered.
Existing draft-linked captures still open the established draft dossier. Generic
counts and organization confirmations now say elementos, covering files and notes.

The synthetic note uses the existing local seen/archive/restore/undo mechanism.
It is not an error, review requirement or financial approval. Only the explicit
example is injected in the development/mock-auth Reception surface. No incoming
message classifier, text-to-expense pipeline, timing-based receipt association,
provider request or backend write is added.

Read-only baseline evidence: WhatsApp intake._claim routes TextMessage through
capture_text; BusinessCaptureStore stores a sealed transport envelope with replay
identity checks; BusinessWhatsAppWorker runs durable conversational turns. Media
captions are passed as source_text with the receipt. The web BusinessCapture DTO
is draft-linked and lacks origin/sender fields. The orchestrator was asked to
confirm the current integrated contracts and persistence, not infer that all
stored messages belong in Bandeja. Greetings/commands/replies stay in messaging;
promoted business notes need an authoritative stable item and original text.
Separate follow-ups require an established link or explicit choice. Any future
Preparar gasto must reuse the existing draft/review pipeline and owner approval;
text is not payment evidence. No implementation authority was implied by handoff.

Eight model tests pass, including caption non-duplication and standalone note
semantics; existing organization tests and focused lint pass. Whole-project tsc
remains blocked by existing broad test/type diagnostics; no diagnostics name
the changed Reception source files.

Default-list refinement: Remitente now has a 180px minimum and 240px cap; Estado
has a 240px minimum and shares spare space with Contenido. Review readiness uses
the neutral pill, while exceptions retain the stronger treatment. Monto/Moneda
default to unchecked and stay independently revealable in their established
positions. This supersedes prior money-visible defaults. Standalone notes show
the accessible no-attachment dash, not visible Sin archivo copy. The unseen
gutter and title alignment are unchanged.

Delivery-level exception titles now use actual subject, or the sole attachment's
filename when subject is missing. Their failure remains in Estado. An unidentified
delivery falls back to Correo recibido, never an assertion of missing documents.
Document rows still use captured identity/filename rather than their email subject.
The orchestrator received the sender contract gap explicitly: authoritative
WhatsApp phone/name and manual uploader identity when available, no supplier
substitution or inferred personal data. Attachment presence is backend-owned.
Nine focused model tests and targeted lint pass.


## Intake dossier and loading layout, 2026-10-27

Row inspection now opens an owned intake dossier using the shared AdaptivePanel
record width, desktop canvas behavior and full-height phone sheet. Original file,
verbatim caption or note text, sender, channel and arrival time remain distinct.
The original starts expanded. Supported Revisar/Resolver/Ver registro actions
continue into the existing financial dossier; inspection alone marks only the
local personal seen state. One intake panel is open at a time. Closing restores
focus to the trigger, with the list as fallback. Source retry keeps keyboard
focus inside the dossier when its retry button disappears.

ReceiptSourcePreview's leased showArrivalContext option defaults to true. This
dossier opts out only of duplicate channel/timestamp copy; original download,
email links, repeat-delivery information and retry behavior remain intact. The
lease has been returned. No financial form, backend, permission or API changed.
The local email fixture does not supply the message-detail endpoint: its real
unavailable/retry state remains visible. Successful original-message rendering
was separately verified with an explicit synthetic local response.

Adjunto is left-aligned with a 104px allocation. The English Attachment header
no longer collides with Channel. Unseen titles use weight 600 versus 400 for seen
items, retaining the reserved indicator gutter.

The loading list now shares the actual row grid, density and optional information
settings, including the combined source layout and compact phone list. Five
non-interactive rows use the shared 300ms delay, shimmer and reduced-motion
behavior. Header selection is disabled while loading. No amount/currency
placeholder appears when those optional fields are hidden. The action placeholder
uses the same footprint without rendering an empty interactive-looking button.

Focused lint and 14 model/source/organization tests pass. Local headless checks
cover desktop/phone receipt, note and email dossiers, existing review routing,
source/body error and retry, full original text, focus return, English header
spacing and loading layouts at 1920/1440/390px. Desktop skeleton grid and row
height match loaded rows exactly; phone content adapts to its actual metadata.
Reduced-motion checks report no animation, no page overflow or JavaScript errors.
Evidence remains ignored under temp/reception-startup, private until checkpoint
clearance. This is local fixture proof, not hosted or persistence acceptance.
