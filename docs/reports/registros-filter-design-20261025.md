# Registros desktop filter design, October 25, 2026

Current behavior is recorded in [Approved Registros checkpoint](#approved-registros-checkpoint-26-october-2026).
That section supersedes earlier implementation descriptions where they differ.
Earlier sections retain the decisions and verification history.

## Local design scope

The founder approved a desktop visual preview of the filter panel, two-month
calendar and removable chips. The follow-up promotes basic named views and
matching exports into pilot scope. This checkpoint implements local UI only.

The advanced filter controls are enabled only in development with mock auth, at
desktop widths. The local date preview also covers phone widths. Filter selections and calendar dates do not query or change the table.
The existing text search and Venta/Gasto selection retain their behavior. Named
views capture those selections, the preview date and advanced filters in memory;
refresh clears them. Export is consolidated in the existing Agregar menu. That
entry retains its existing period-based behavior; filtered-result export still
needs wiring. The overview cards retain illustrative counts. Hosted wiring is unchanged.

## Calendar interaction checkpoint

The date preview uses typed dates with an explicit locale format and no native
date popup. Drafts apply only on confirmation; Escape or dismissal discards them.
Presets cover today, yesterday, inclusive last 7/30 days, the previous completed
calendar quarter and custom dates. All ranges keep the 366-day bound.

The shared range engine supports same-day, reverse and cross-month selection,
hover previews, endpoint dragging, arrow-key cursor movement, Enter selection,
Page Up/Down by month and Shift by year. Desktop shows two adjacent months, or
three on a wide container. A narrow dossier shows one. The phone preview uses a
full-screen sheet with vertical months, sticky Today navigation and pinned
confirmation. It does not open the keyboard automatically.

Existing embedded calendar callers share this presentation and engine while
retaining their current draft callbacks and their own apply/export actions. The
old exported pickDay helper retains its earlier contract. Backend queries,
export semantics and single-date editors were not changed.

Focused verification: 51 tests passed across the range engine, calendar, date
preview, existing period control and shared sheet suites. Scoped ESLint and
`git diff --check` passed. Live viewport/theme review belongs to the parent
design lane; no hosted acceptance is claimed here.

## Product decisions for later wiring

- Page period scopes the overview cards. Table search and filters do not rewrite
  those overview counts. Card selections become visible removable table filters.
- Distinguish record kind (Venta/Gasto), document kind (invoice, receipt, credit
  note) and fiscal classification. The preview fiscal options are illustrative,
  not a complete supported catalogue.
- Attachment presence is independent of NCF completeness, approval and matching.
- Filter groups include review, attachment, original currency and amount,
  counterparty, category, account, document kind and fiscal classification.
- Counterparty and account selections must use canonical identities when wired.
- The pilot reporting loop is filter, inspect count/totals, save view and export
  the same results. Views remember filters and columns and refresh their results
  as records change. Export captures a fixed result set at a point in time.
- A thin monthly accountant-handoff check and customer balance/payment history,
  including basic partial payments, remain pilot requirements. This UI slice
  does not implement them.

## Backend requirements and hosted acceptance for the later handoff

- Authorize every query, saved view and export against the selected Business and
  current member access. Verify isolation by switching Businesses and users.
- Use one filter definition for rows, matching-record count, totals and export.
  Include pagination beyond the visible page; export must not fall back to the
  whole period when additional filters are selected.
- Keep currencies separate. Amount ranges use original currency. Only show
  subtotal, tax and total where data is captured and comparable. Credits and
  cancellations must not inflate totals; linked invoices and payments must not
  be counted twice.
- Persist named views with filters and column choices. Confirm reload and
  cross-session restoration, and deliberate handling of removed options.
- Export must identify the applied filters, captured records and capture time.
  Later record changes must not silently alter an already produced handoff.
- Prove the scenario: October expenses for a selected supplier, in DOP, without
  a document; resolve a record, observe updated counts/totals, restore the saved
  view and export exactly the intended records. Verify permission-denied,
  empty and partially captured data cases.

No backend, deployment, migration, hosted acceptance or orchestrator handoff was
performed in this design slice.


## Phone list and pagination local implementation

The development/mock-auth saved-records preview now paginates only the actual
loaded records. It sorts by record date with a stable kind/id tie before slicing.
The default is 25 rows; 50 and 100 are available through the shared custom picker.
The footer shows the loaded matching range/count, bounded numbered links and
first/previous/next/last controls. No rows or totals are generated for the server.

One CSS container query at 700px controls the table/list presentation. A resize
observer reads that query result so only one presentation mounts, preserving
unique row refs. The narrow two-line list aligns full signed currency amounts,
labels the record date and exposes truncated names/status text through the
existing tooltip. Proof stays on the second line. The source list stays mounted beneath the shared phone sheet. Plain expense
glances in this local preview receive only the selected row facts explicitly;
they do not call the unavailable local detail path or fabricate notes, payment
history, timestamps or revisions. Receipt/draft targets retain their existing
detail renderer. Hosted persisted detail acceptance remains outstanding.

Query, kind, date/advanced-preview changes, restored views, sort and page-size
changes reset page 1. Density changes retain the page. Empty-result recovery
retains sort and page size; a shrinking loaded set clamps the page safely.
Loading retains the existing skeleton and omits a count. Bank matching is unchanged.

Focused synthetic tests cover 65 supplied records across three pages, stable
sorting, resets, density preservation, 50-row selection, empty-result recovery,
zero/last-page boundaries, shrink clamping and phone sheet/list retention.
Browser viewport checks remain separate. No URL persistence, server page/count
contract, dataset-version banner, selection/export scope or cross-session saved
view persistence is claimed. Date/advanced preview filters still do not query
rows or change source-period totals. Reloading a loading branch may reset this
local page state; preserving that across hosted refresh belongs to later wiring.

Live browser verification on the existing port 4387 preview covered desktop,
391px and 320px phone widths. At a 1100px desktop viewport, opening a dossier
left a 552px records container and switched the table to the list. Both phone
widths stayed within the viewport, with aligned amounts and consistent row
heights. The page-size picker remained usable near the bottom. A 50-row setting
survived a zero-result search and a two-result search. The expense glance and
attached-receipt sheet opened and closed back to the source list, restoring focus.
Multi-page behavior used 65 synthetic rows in component tests; the live preview
kept its six actual loaded records. No hosted or backend acceptance is claimed.

## Phone list and pagination contract, October 25, 2026

These are the broader agreed requirements; the local implementation above
covers only the named preview behaviors, not hosted acceptance. This note does not declare a checkpoint or authorize a
handoff. The inspected frontend baseline is `ba5cf96a7`.

### Phone and narrow-container presentation

Keep the seven desktop columns: Contraparte, Fecha, Monto, Detalle, Categoría,
Cuenta and Comprobante. Below the table container's useful width, show a compact
list instead of shrinking the table or relying on horizontal scrolling. Start
with a 700px container threshold and verify real content at that boundary,
including when a desktop dossier narrows the list. Use one container query.

Each row has a fixed, right-aligned amount slot with tabular figures and an
explicit currency. The first line shows the counterparty and amount. The second
line shows the relevant state and a labeled date. A due date appears only when
provided by the record. Otherwise identify the record date. Do not substitute
a record date for a due date or confuse review state with payment state.

Keep rows thumb-sized, separated by hairlines, with consistent amount alignment.
Long names truncate. Amounts remain complete. Proof and action icons must not
move the amount slot. Do not put technical IDs first. Label ambiguous values,
move sorting into a control, and keep the same active sort as the desktop table.

Tapping a row opens the full record in the shared phone sheet. It exposes IDs,
notes, documents, payments, balance, history and permitted actions as supported.
A quick glance does not navigate to a new page. Keep any small inline disclosure
bounded; the full record belongs in the sheet. Closing restores the source row.
This new Registros requirement supersedes the older phone-full-page rule for
record glances in DESIGN.md. It does not change other flows by implication.
The design lane must update that scoped rule alongside implementation.

Illustrative layout, not a claim of current field support:

```text
[Buscar registros...]       [Filtros] [Ordenar]

Colmado La Esquina                 RD$10,000.00
Cobro parcial                 Vence el 4 de mar
------------------------------------------------
Ferretería La Esquina               RD$2,400.00
Por aprobar                  Fecha: 24 de oct

26–50 de 238 registros           [25 por página]
[Primera] [Anterior] [1] [2] […] [10] [Siguiente] [Última]
```

On small widths the footer can wrap into aligned lines. Page numbers remain
bounded and direct page access remains available.

### Workspace navigation and result scope

Preserve the order of overview cards, controls, compact financial summary,
records, and pagination. Use numbered pages, Anterior/Siguiente, first/last
access and a truncated page-number range. Default to 25 rows with 50 and 100
choices. Show the range and filtered total only when known. Loading must not
invent a count or collapse the records area.

Search, filters, sorting and page-size changes reset to page 1. Column and
density changes preserve the page. Keep active filters visible and removable.
Compact totals cover the entire matching set, never only the displayed page.
Overview cards keep their separate selected-Business and page-period scope.

Represent the Business, query, date basis, filters, currency, sort, page size and
page in the URL where appropriate. Opening a detail and returning restores the
query, selected row and scroll position. Store a stable record identity as the
return anchor. If it is deleted or no longer matches, explain the change and
restore the nearest valid position. Saved views remember the working setup,
including filters, columns, sort and page size, but open on page 1.

Do not insert new rows while a person reads a page. A reliable server change
signal enables the proposed 'Hay cambios nuevos · Actualizar' state. After a
refresh, try to restore the anchor and explain any changed position. If the page
is no longer valid, show recovery instead of silently shifting its results.
The design must cover loading, no results, request failure, last page, and an
invalidated page, using explicit fixtures until the contracts exist.

Selection uses explicit stable record IDs. If it spans pages, keep its total
visible with 'Limpiar selección'. Changing Business clears selection. Filter
changes must clear selection with feedback or explicitly expose retained hidden
selections; they must never remain silently active. The design must settle that
choice before wiring it.

'Exportar resultados' means every matching record. 'Exportar seleccionados'
means the explicit selected IDs. Neither means the current page. Do not present
unsupported export scope as working. Amounts retain currency, totals stay
separate, and amount ranges name their currency. A mixed-currency amount sort
must not imply a common value without a defined conversion basis.

### Current gaps and acceptance ownership

| Control or behavior | Current inspected behavior | Remaining work and owner | Acceptance check |
| --- | --- | --- | --- |
| Narrow list | `TransaccionesPanel` chooses a list using `isBelowTablet`. `RecordsList` centers the amount beside text; a proof icon can move its position. | Frontend design owns the container switch, aligned rows, labels and sheet interaction. | Narrow the table on desktop and phone. Amounts stay aligned, full currency remains visible, and closing detail restores the row. |
| Numbered pages | Saved records render the locally available set and its length. The bank path uses `LoadMore`. Neither proves this numbered-page contract. | Frontend owns controls and states. Orchestrator owns the query/count contract. | Reload page 3 directly; show its accurate range and count. First/last and truncated links work at 25, 50 and 100 rows. |
| Filtered totals | Search and record kind filter rows locally. `RecordsSummary` still receives the source period totals. Advanced filters and named views remain preview state. | Orchestrator owns shared query semantics and persistence. Frontend consumes the same query for controls and totals. | Supplier plus DOP plus no-document filters produce matching rows, count, totals and export across multiple pages. |
| Return position | Saved records have partial expense-row focus restoration. It is not full URL/query/scroll restoration. | Frontend owns URL and anchor restoration with backend invalid-page information. | Back restores the query and row. Removing that row gives an explanation and nearest valid position. |
| Data changes | No shared Registros result-version contract has been verified for this requirement. | Orchestrator must identify an existing reliable signal or define the smallest missing implementation. Frontend owns refresh/recovery presentation. | Concurrent changes never silently insert or shift the viewed rows. Refresh restores the anchor or explains recovery. |
| Export scope | `business_export.download_export` accepts only `start`, `end` and optional `draft_id`. Other query fields are rejected. | Orchestrator owns arbitrary-filter and explicit-ID export contracts. Frontend owns scope labels and feedback. | Filtered exports and selected exports contain exactly their intended records, including records beyond page 1. |

The inspected saved-records path fetches `GET /business/expenses` with `from`
and `to`, and fetches sales through the same endpoint with `kind=income`.
Its `{items: BusinessExpense[]}` response and frontend adapter expose no numbered
page, filtered total or server result version. Overview totals arrive separately.
See `web/lib/business-api.ts` and `transacciones-adapter.ts`.

The bank path uses `GET /business/bank/movements` with `period_start`,
`period_end`, `segment`, optional `currency`, `limit` and `cursor`. Its response
has `items`, `next_cursor`, `totals`, `counts` and `other_currencies`. Those
`counts` are period-wide across segments and currencies, not the requested
filtered-result total. No result-version field appears in that response schema.
The Business context's client revision triggers a refetch; it is not a server
invalidation contract. These findings cover the inspected paths, not every API.

### Required checkpoint handoff, when authorized

The design lane must send the following requirements with the exact checkpoint
SHA. Do not hand off only a list of preview limitations.

1. Preserve direct numbered-page navigation and filtered counts for Registros
   and Invoicing. The orchestrator first evaluates indexed offset queries for
   the pilot. Cursor-only navigation needs an explicit explanation of which
   approved behavior changes. Supported sorts are allowlisted, end in a unique
   record key, and define ties and null ordering. Measure representative
   filtered queries rather than assuming every column is cheap to sort.
2. Use one query definition for rows, count, financial totals and exports.
   Include Business, date basis, filters, currency and sorting. Pagination
   limits displayed rows only. Enforce current access and Business isolation
   on every request, including exports. A saved URL grants no access.
3. Deterministic ordering does not prevent offset drift between requests.
   Identify the reliable invalidation/version signal and mark any missing
   implementation as a dependency. Do not promise stable cross-page browsing
   without proof or keep a database transaction open while someone browses.
4. Define whether export captures records at request time or processing time.
   Use a consistent read or captured dataset and report generation time and
   scope. Reusing filters alone cannot reproduce an earlier result after data
   changes. A frozen review session is a separate feature, not an implicit
   requirement for a large snapshot system.
5. For each control, supply expected behavior, actual endpoint and field
   support, preview-only or missing behavior, owning lane and exact acceptance
   check. Recheck this document against the checkpoint SHA. Explicitly retain
   the period-only export gap until arbitrary filtered export is proven.
6. Include hosted acceptance for direct-page reload, Back-to-row restoration,
   tied sort values, filter and page-size reset, zero results, deleting the last
   row on the last page, concurrent changes, revoked access, mixed currencies,
   and exports spanning multiple pages. Test Business isolation for rows,
   counts, totals and exports. No hosted acceptance is claimed by local UI tests.

The eventual packet must name the exact endpoint/field contract, outstanding
backend dependencies, frontend ownership and checkpoint SHA. Database query
implementation remains the orchestrator's responsibility. This update records
requirements only; it makes no backend, UI, deployment or handoff changes.

### Phone filters and local table preferences (2026-10-25)

The development mock preview now opens Filters on phones in the full-height shared sheet. Group navigation and Back retain one draft; Clear is staged until Apply, while close/Escape discards. Registro replaces the separate phone Tipo picker. Bulk checkbox selection still acts on visible search matches and preserves hidden choices. Date fields keep the format in their placeholder and show only actual validation below.

Desktop saved-record preferences use one local `{ order, hidden, density }` value. Contraparte is fixed first, Monto remains visible, and the five other columns can be hidden. Grips support pointer drag and Space/arrow keyboard movement; Escape restores a grabbed order. Headers, cells and widths use the same visible order; Comprobante pins right only when last. These choices do not reset the local page, and named views capture them. Phone rows and bank matching remain unchanged. This preview does not write table preferences to `/me`, persist across refresh, or change hosted query/export semantics. Existing production density persistence remains separate and unchanged.

### Results strip and workflow column (2026-10-25)

The local development/mock preview uses a separate eight-column registry. Defaults show Contraparte, Fecha, Monto, Tipo, Categoría, Estado and Comprobante; Cuenta is available but hidden. Tipo shows only the record kind. Estado is an explicit illustration keyed by the exact `fixture-space` Business and the existing `gasto`/`venta` fixture IDs (`exp-gas`, `exp-hosting`, `exp-lunch`). Other Businesses and unmapped rows show unknown status and are excluded from confirmed totals. No backend RecordRow, adapter, bank-matching column or API contract changes.

Workflow and financial eligibility remain separate. The gas purchase illustrates a confirmed amount that still needs review. Personal records remain excluded; unconfirmed amounts and unavailable eligibility are counted separately. The quiet results strip summarizes the entire loaded set after the existing local text/kind filters, before pagination. Exact minor-unit arithmetic keeps currencies separate. Document amounts display their original magnitude with currency and the existing privacy masking hook; they do not describe cash received/paid or imply a payment.

Advanced filters and the local date draft still do not query or filter this row set, and named views remain local memory only. The illustrative workflow/eligibility mapping is not hosted verification. Production needs authoritative workflow, inclusion reasons, result counts and exact-result aggregation from the orchestrator. Static overview cards above the toolbar remain their previously scoped illustration and are not the source of these counts.

### Compact money cards and shared summary settings (2026-10-25)

This correction supersedes the earlier results strip and four-metric customization. Only Sales and Expenses remain. The cards use the overview family's icon, short uppercase label and prominent value, at a smaller size with subdued theme colors. The repeated visible summary heading, count and exclusion legend are removed. Each money card retains its own eligibility and exclusion context, exact separate currencies, and privacy masking. Unavailable money never becomes zero.

Summary is the third segment of the existing desktop table Settings. On phones the same toolbar control opens a shared sheet for summary only; it does not pretend to change the phone list's columns or density. Checkboxes and reorder controls edit a draft. Apply commits, while close or Escape discards. An empty selection hides both cards; Settings remains available to restore them. Ordered metric selection belongs to the same local view-preference value as columns and density, so named views now capture and restore it. Nothing persists across refresh or writes `/me` in this preview.

Currency remains one choice inside Filters. Its existing currency/amount draft is now owned above both the toolbar and results. Applying a currency narrows actual loaded rows, cards and pagination counts together. Optional bounds compare exact original-currency amount magnitudes without conversion; negative expense storage values do not reverse the filter. A currency-only chip says Moneda/Currency; bounds use Moneda y monto/Currency and amount. Removing the chip or clearing a no-result view resets the same source. Other advanced filters and the date preview remain illustrative and do not filter the loaded rows.

With no currency selection, each card shows at most two currency amounts. A read-only disclosure exposes the rest in a scroll area capped at 144px, so a long currency list cannot grow the page without bound. It has no separate currency selector and never combines currencies. The document/count metric options and their unused UI/model fields are removed.

The future backend handoff must provide authoritative result aggregation and eligibility, currency/range filtering, and the persisted preference and saved-view contract. Hosted acceptance must prove Business isolation, exact original-currency ranges, filter-wide totals across pages, preference recovery, no-result clearing and privacy masking. Existing fixture-only financial eligibility is still an illustration, not hosted verification. No backend work or hosted acceptance is claimed here.

Focused checks cover Settings draft/apply/discard, empty selection recovery, desktop keyboard/pointer reorder, phone touch reorder, thirty-currency disclosure, exact large-number bounds, and actual rows/cards/footer/chip clearing in EN and ES. Existing pagination, saved-view and legacy filtering checks remain in the focused set.


### Three-part summary and overview filters (2026-10-25)

This slice supersedes the two-card summary above. The existing record-kind filter owns summary mode. Todos hides the financial summary. Sales show Facturado, Cobrado and Por cobrar. Expenses show Gastos, Pagado and Por pagar. One rounded container has three columns on desktop and three label/amount rows on phones. The result count remains in pagination. A small information disclosure beside the first metric explains exclusions. No repeated scope line or footer legend is shown.

Multiple currencies collapse into one read-only disclosure with three amounts for each currency. Moneda remains exclusively in Filtros. The summary does not convert or sum different currencies. Resumen settings now contains one draft visibility checkbox. Apply commits it locally and dismissal cancels it. Local named views remember visibility with their existing working setup. The old metric catalogue and reorder controls are removed.

The top cards now count the loaded records for the selected Business and the local page period before table search, kind, currency or review filters. Clicking a top card sets the same review filter used by Filtros. Its chip can be removed. Search and currency do not rewrite the overview. Review and currency filters compose before rows, pagination and financial summary. Any record with unknown workflow makes overview counts unavailable instead of presenting an incomplete total.

The date draft now lives in the panel with the other applied filters. Its inclusive range checks the record activity date. Missing or invalid activity dates are not replaced with upload dates. A named view restores that period and starts from page one. This still filters only the currently loaded source records. Widening the range cannot retrieve records outside that source result. An empty local period offers Restablecer período, which restores the loaded provider period without an API call. Clearing table filters does not silently change the period. No server query or hosted count is added by this slice.

Partial-payment examples are explicit local fixtures keyed by record kind and ID. The DOP sales fixture has 1,400 collected against 2,100 invoiced. The DOP expense has 1,200 paid against 2,100, and the USD expense has 12 paid against 24. Each allocation includes its expected original amount and currency. A changed amount, another Business, an unknown allocation or an invalid payment never produces a fake paid amount or balance. Missing settlement data makes paid and balance unavailable for that currency. Exact arithmetic uses minor units. Personal and unconfirmed records remain excluded with an explanation.

The amounts are read-only in this visual slice. The connected payment/document explanation and amount-click drill-down remain pending. The future backend contract must supply the full Business/period overview, the shared table query, financial eligibility and payment allocations with stable document IDs. Sales summary needs a defined invoice record scope rather than assuming all income is invoiced. Hosted acceptance must prove partial allocations, original-currency arithmetic, unknown versus zero, complete filter-wide totals across pages, overview stability under table filters and matching exported scope. No backend work or handoff occurred here.

### Record cell refinements and local annotations (2026-10-25)

The development/mock Registros preview now shows explicit activity dates with the year on desktop, narrow rows and the loaded-record glance. Dates are validated calendar days; invalid or missing values stay unknown. Estado uses the overview's review, approval and ready palette with a colored text label. Registros is an explicit exception to the earlier global status-dot rule and has no inner dot. Ready rows say Listo or Ready; the top export card keeps its full label. Workflow and payment state remain separate.

Desktop Monto contains only the exact number, with the existing privacy mask and right-aligned tabular digits. The adjacent required Moneda column renders the original currency through `currencySymbol`. Currency filters retain currency codes. The table registry owns the new columns, labels and widths. Moving Monto keeps Moneda beside it. Notes contain only the current local note and a tooltip. The shared local editor saves explicitly and discards drafts on dismissal. A compact narrow-row menu exposes Notes and Attachment without nested buttons.

Adjunto replaces the preview's Comprobante label. Known missing files offer a 44px plus target. Unknown remains unknown, and existing evidence follows its original record path. Local selection reuses the file-type helpers and workspace limits, checks file name, type and size, and allows a local preview. No upload or network write occurs. The in-memory annotation map keeps note text and a selected File under Business plus stable record kind and ID. It survives local filters, pagination, viewport changes and the loaded-record glance, but not refresh. Object URLs exist only while a file preview is open and are revoked when replaced or closed. Existing prepare permission controls editing.

Later backend work must supply the authoritative current note and attachment metadata for each stable Business-scoped record, including kind when IDs overlap. Define note length and normalization, attachment type/name/size limits, permissions, revision/conflict handling, save errors, upload/scan failure states, and authorized evidence URLs. Activity owns the audit history of note edits and removals. An idempotency key must prevent duplicate retry writes, and an optimistic version conflict must protect another person's edits. Never silently overwrite a newer version. The current UI shows no history. Save must not claim success before durable storage succeeds. Re-read must recover the saved note and attachment after refresh. Prove Business isolation and revoked/read-only access for reads, edits, uploads and downloads. A local file must never imply a hosted attachment or change fiscal completeness by itself.

The activity-date field and workflow status still require an authoritative contract. Preserve date-only semantics across time zones, unknown versus absent attachment state, exact original-currency money, and the distinction between workflow and payment status. Update future query/export/preferences acceptance for the new currency, notes and attachment columns without changing the current period-only export. Related-record grouping and a new writing flow remain outside this slice. These are requirements for the later handoff; no backend work, hosted acceptance or handoff is claimed here.

Local verification passed 80 focused tests across eight files, including note save/cancel, Business and record-kind isolation, filter/viewport retention, phone sheets, attachment validation and record association, no network writes, object URL cleanup, keyboard routing, exact dates/money, currency pairing and existing page/filter behavior. Scoped ESLint and `git diff --check` passed. Full TypeScript checking still reports the existing test-runner declaration baseline; changed production files have no diagnostics. Browser evidence is reviewed separately at the current local preview.

Independent review found and corrected an upward column-move boundary. Moving a column above the Monto/Moneda pair now places it before both, while moving Monto keeps its pair intact and Contraparte stays fixed. Added regressions cover those movements and ordinary PDF/PNG names, path separators and control characters. The exact regex extracted from the source accepts normal names and rejects unsafe names; no filename-validation code change was needed.

After that correction, six targeted checks across four files passed, including the existing table-settings pagination/reorder interaction. Scoped lint and the diff check passed.

Browser verification on the existing port 4387 passed on desktop and a 391px phone viewport in light and dark themes. The final dot-free labels were checked on desktop and phone. A local note remained attached to its expense through filtering and viewport changes; Cancel preserved the saved value. The phone menu opened the shared sheet. A synthetic PNG could be selected, previewed and saved locally to one expense while the same-ID sale retained its add-file action. EN/ES label paths are covered by tests. No hosted write or new server was used.

### Independent required columns, 26 October 2026

Monto and Moneda start adjacent but move independently. Both remain required. The column renderer now respects the selected order instead of forcing the pair together. Keyboard handles explicitly receive focus on pointer press and ignore repeated Space keydown events. The visible hint identifies the focused handle step and indicates when a column is picked up.

Local verification on port 4387 covered consecutive keyboard moves without refocusing, placement, cancellation, and unchanged Monto position while moving Moneda. The focused suite passed 60 tests; the added rendered drag-event case also passed. Mouse-drag automation did not produce a confirmed live reorder, so that live pointer check remains unverified. No backend, persistence, export, or hosted behavior changed.


### Local sorting and saved-view contract gap, 26 October 2026

The preview adds one sort preference shared by desktop headers, phone controls and local named views. It supports activity date, exact amount magnitude and locale-aware counterparty in both directions. It sorts all filtered loaded rows before pagination, keeps invalid values last, and breaks ties by record kind and ID. Changing sort resets the page without changing counts or totals. Amount order requires one known currency across the full filtered result. If that stops being true, the view explicitly falls back to newest date order while retaining the chosen amount order for a later single-currency result.

The integrated report-view API currently supports schema_version, filters, column visibility/order and date_desc only. The new sort choices and chosen summary preferences remain local and are not persisted through that API. The orchestrator must extend and allowlist the sort contract before hosted wiring, preserving equivalent rows/count/totals/export scope, deterministic ties, null ordering and original-currency meaning. Hosted acceptance must verify the additional sorts, direct-page reload, saved-view restoration, currency-filter removal during amount order, page reset and export agreement. No backend change or external handoff occurred in this slice.

Focused verification passed 78 tests across five files, including exact large-amount ordering, missing values, deterministic ties, mixed-currency fallback, shared desktop/phone sort state, page reset and local saved-view restoration. Scoped ESLint and the diff check passed. Full TypeScript checking retains the existing bun:test declaration failures; none names a changed production file. The light ready-to-export overview background now tries #8EB69B while retaining neutral card ink and selection edges; the Listo badge and dark treatment are unchanged.

### Evidence, intake and matching checkpoint requirements, 26 October 2026

This section appends the current decisions without rewriting the historical checks above. The inspected frontend baseline is `58c2f0a52` (`58c2f0a5250f6a20ad097f4367225cdeadd79b79`). The design checkpoint SHA remains pending the parent commit. A future handoff must name its exact committed SHA and the proof captured there; this section is not that handoff. The orchestrator's verified integration report supersedes the older unmerged status for #1387: it is merged at integration commit `8c993ef`. That delivery does not supply an attachment-to-existing-activity API or activate bank matching.

The product invariant is one activity, its evidence and its linked payments. Keep new-document intake, supporting evidence and bank matching as three distinct actions. Adjunto is the approved name. Several supporting attachments are allowed per activity: Add appends and never replaces. Preserve original custody and Business scope. Explain an already-linked conflict instead of silently moving a document. No unlink control is enabled before its contract exists. A cash purchase need not have a bank movement, and an unmatched document is not automatically incomplete or unfit for approval.

The endpoint paths below are the existing public contracts in `docs/API_CONTRACT.md` and `docs/contracts/business-bank-matching.md`. Readiness describes the inspected contract and local preview, not hosted acceptance.

| User intent and visible behavior | Existing contract or missing capability | Evidence, activity and payment effect | Permission, retry, conflict and undo | Owner, remaining dependency and acceptance |
| --- | --- | --- | --- | --- |
| Add a new document through the existing intake and review its result. | `POST /api/v1/business/receipts`; `POST /api/v1/business/receipts/{id}/prepare`; `PATCH /api/v1/business/receipts/{id}/review`; `POST /api/v1/business/receipts/{id}/confirm`. Reuse this flow. | Capture preserves evidence. Review/confirm follows the existing canonical activity flow. Upload alone proves neither payment nor approval. | Existing Business intake/prepare rights and owner approval remain canonical. Upload requires `Idempotency-Key`, with byte identity returning the existing receipt. Review/confirm uses the current version; stale review is `409 stale_version`. Confirm is idempotent and must record one expense. | Frontend lane reuses the intake; the orchestrator assigns any backend gap before work. Accept repeated upload/retry and concurrent confirm without a second activity. |
| Open evidence already linked to a record. | `GET /api/v1/business/receipts/{id}` and `GET /api/v1/business/receipts/{id}/source`; the preview follows the existing record path. | Read only. A source-download failure does not remove the relationship or turn it into Sin documento. | Canonical Business read authorization applies. Retry source access without changing evidence or payment state. The source contract can return `422 document_source_unavailable`; keep the link visible and explain the download failure. | Frontend lane owns presentation; existing source owner owns availability. Accept linked-but-unavailable evidence, successful retry and cross-Business denial. |
| Add another supporting file to an existing activity through Adjunto. | Public linking capability is missing/unverified. The documented preparation finalizer has an internal versioned existing-draft target, but current web upload uses `target: null`; that is not a public attachment-link API. | Append evidence only. Keep every existing attachment, amount and payment allocation. Do not create or confirm another purchase as a substitute for linking. | Existing prepare capability gates editing. Backend must define the canonical activity target, link idempotency, revisions, upload/scan failures and conflicts. Retrying must not duplicate evidence or activity. No unlink control yet. | Frontend lane owns the local design; orchestrator must assign the backend/API owner and approve the link contract before wiring. Accept several appended attachments, refresh recovery and unchanged activity count/amount/payment state. |
| Choose a document already received instead of uploading it again. | `GET /api/v1/business/receipts?view=inbox\|all` and receipt detail exist. No verified public candidate-eligibility/link contract exists. Keep the selector unavailable. | Reuse original custody and append an evidence relationship; never duplicate the activity or move an existing relationship silently. | `records.inbox` is incomplete because inbox excludes confirmed/dismissed documents. `ReceiptSummary.expense_id` is not proof of eligibility. Require authorized candidates, explicit already-linked conflicts, idempotent link/retry and version handling. | Backend/API owner remains to be assigned by the orchestrator. Frontend may design the unavailable path. Accept receipt-before-movement and receipt-after-movement cases, already-linked conflicts and cross-Business denial. |
| Select and inspect a local file in this design preview. | In-memory annotation state and object URLs only; no upload or durable link is called. | Preview only. It disappears on refresh and changes no evidence filter, activity, amount, fiscal status or payment. Several local files can be appended, with duplicate bytes suppressed. This does not demonstrate durable multiple-attachment support. | Existing prepare capability and workspace file limits apply. Invalid files stay unsaved; closing discards the draft. Revoke object URLs on close/replacement. Explain local readiness next to the selection and saved local presentation. | Frontend lane. Accept record-kind/ID and Business isolation, refresh loss, no network write, validation and URL cleanup. |
| Igualar a suggested or manually selected bank movement. | Existing default-off `POST /api/v1/business/bank/suggestions/{suggestion_id}/confirm`, `/decline`, and `POST /api/v1/business/bank/movements/{line_id}/match`. | Links an existing movement to existing activity. Confirm/match currently writes whole-document pagado/cobrado settlement. Decline confirms nothing. No new purchase is created. | Existing `prepare` decides and `read` lists. Decisions require `Idempotency-Key`; same key/decision replays. Manual match requires the same Business, sense, currency and full amount. Explain already-matched/declined conflicts. Show counterparty, date, amount, currency and source account where known; ambiguous suggestions remain unconfirmed. | Existing matching owner, coordinated by the orchestrator. Release remains held until settlement writes agree with partial-payment allocations. Accept ambiguous/no-match cases, receipt-first/movement-first order, same-currency/full-amount limits and no automatic confirmation. |
| Undo a confirmed bank match. | Existing default-off `POST /api/v1/business/bank/movements/{line_id}/unmatch`. This is not evidence unlinking. | Ends the match and restores its saved prior settlement status, date and method; it does not delete the original file. | Existing prepare capability and `Idempotency-Key` apply. Explain the payment consequence before confirmation. Existing conflicts and history remain canonical; a retry must not restore settlement twice. | Existing matching owner. Orchestrator must reconcile undo with allocation history before release. Accept restoration of the prior state and prove a partial payment never silently becomes fully paid. |

The receipt list and detail types already expose document ID, file metadata, channel, received time, review facts, status and duplicate/expense references. `ReceiptDetail` adds canonical record context, draft ID and version. `BusinessDataSource.receipts("all")` is an existing authorized read, while the mounted workspace currently loads `receipts("inbox")`. Neither response defines which documents may be linked to another activity. Do not infer eligibility from visibility, absence of an expense ID or a local selection.

For the local Con documento/Sin documento filter, use only the loaded `RecordRow.hasProof`: true for Con documento, false for Sin documento, and unknown excluded from either restricted choice. The unrestricted view retains all states. Filter the full loaded set before pagination and summaries. A local File never changes `hasProof`; a failed source download never clears it. Evidence presence says nothing about verified facts, approval, fiscal acceptance or payment. Sin movimiento vinculado remains a different condition.

The future checkpoint acceptance record must cover repeated upload; evidence appended to an existing activity without duplication or replacement; receipt arrival before and after a movement; ambiguous suggestions; already-linked documents; legitimate cash purchases without matching; cross-Business denial; linked evidence with unavailable download; retry/conflict handling; and partial payments not silently becoming fully paid. Record one owner and exact proof for each row before wiring or release. Any future unlink action first needs its own contract, permissions, retry/conflict behavior, preservation of original files and explicit payment consequences.

Saved metric/widget preferences and the added alternate sorts remain backend gaps. The merged report-view delivery does not establish support for arbitrary widgets or all local preferences; the received contract currently permits `date_desc`, not every local sort. Extend and allowlist the shared rows/count/totals/export and saved-view contract before claiming persistence. Preserve the compact metric cards and do not imply unsupported financial treatment.

The future handoff must label each behavior wired, preview-only, backend-dependent or release-held and name its exact checkpoint SHA. Merge, migrations, deployment, matching activation and fiscal-provider activation keep their existing holds. Channel-access resolution remains separate. This documentation performs no backend work, hosted change, activation or actual handoff.


### Local sweep completion, 26 October 2026

Desktop and phone inspection covered both themes, the toolbar at narrow desktop
width, keyboard column movement/cancel, search empty state, review-card toggle,
attachment filters, note counter, calendar validation and nested sheet return.
The attachment form now uses the receipt-style drop zone, local multi-file
selection with byte deduplication, one 8px-radius full-width footer CTA and one
divider. File picker, drop and paste share validation; none starts receipt intake.
The visible local-only notice remains until a durable evidence-link contract is
implemented. Existing original evidence still opens through its authorized path.

Command-K now focuses Registros search without opening the global search. Open
overlays keep focus. Home keeps its global search. The records loading component
matches selected columns/order/density, the narrow two-line list and pagination.
For visual inspection the local mock briefly rendered the real pending component;
that forced condition was removed before commit. Desktop light/dark and phone dark
loading captures are local evidence, not hosted proof.

Focused verification: 65 passing tests across 10 files, scoped ESLint and clean
whitespace checks. Whole-project TypeScript remains blocked by the existing test
declaration/target errors; it is not a clean repository-wide typecheck. No new
production-file diagnostic was reported for the added components. No backend,
hosted change, handoff, matching activation or fiscal activation was performed.

### All-time scope clarification, 26 October 2026

The approved Todo date option includes every authorized record for the selected
Business, including records older than one year. It has no date cutoff. The
custom calendar's 366-day limit does not apply to Todo. The legacy
`ALL_FROM = "2000-01-01"` sentinel is not the product definition of all time.

Keep numbered pagination and the 25, 50 and 100 row choices. The backend must
return a bounded page of matching rows. Do not fetch all history and slice it
in the browser, or walk every backend page before displaying the first page.
Counts and financial totals cover the entire matching set, independent of the
page. Overview counts retain their separate Business and page-period scope.
Selecting Todo resets navigation to page one and preserves the other filters.

This is a requirement for the later backend connection. The current local
preview filters and paginates already-loaded records, and cannot prove complete
all-time coverage. The current RangePicker preset list also lacks a Todo entry.
Neither runtime behavior nor backend wiring changes in this clarification.

Acceptance must include records from several years, more than 100 matching
records, direct access to later pages, and a reload with Todo selected. Verify
that older records remain reachable, each row response respects the page size,
and full-result counts, totals and filtered export scope agree. Existing export
range limits remain explicit until the export contract supports this scope.

### Metric shelf and currency dossier, 26 October 2026

Approved option one replaces the table-like summary with three quiet metric
cards. Each shows at most two currency rows. A shared action appears only for
three or more currencies and opens the complete read-only breakdown in the
existing dossier, or the shared phone sheet. The component reuses the same
settlement summary for both presentations. No calculation or currency support
was added. Canadian-dollar support remains outside this design change.

The summary still appears only for sales or expenses and can be hidden in view
settings. Current amounts and allocations remain local preview behavior. This
does not prove complete API totals, payment linking or arbitrary filtered exports.

Local verification covered desktop and phone card layouts in light and dark
themes, with Spanish and English copy. A temporary three-currency presentation
fixture verified the full dossier and phone sheet, unknown settlement values,
Escape dismissal and focus restoration; the fixture was removed afterward.
Fifteen focused tests and scoped ESLint passed. No backend work or handoff occurred.

## Approved Registros checkpoint, 26 October 2026

The founder approved this design checkpoint, its commit/push, and handoff to the
Integration Orchestrator. This approval covers the local frontend design. It does
not authorize merge, backend implementation, migrations, deployment, bank matching
activation, fiscal activation, or production changes. The exact pushed checkpoint
SHA accompanies the handoff message. This report and DESIGN.md travel with it.

### Current surface behavior, including interactions absent from a screenshot

| Area | Current local preview behavior |
| --- | --- |
| Overview | Por revisar, Por aprobar and Listos para exportar summarize the selected Business and page period using explicit fixture metadata. Table search and filters do not rewrite those counts. Clicking applies a removable Revisión chip. Clicking the same selected card clears that filter. Clicking another replaces it. Other filters remain. |
| Toolbar | Desktop keeps Vistas, search, date and Filtros, with Agregar and table settings on the right. The Agregar label collapses at constrained desktop widths while plus and chevron remain. The main button and chevron have different actions. Export lives inside that menu, not a duplicate toolbar button. |
| Search | Command-K focuses Records search, not Home omnisearch, and respects open overlays. Local search now matches counterparty names, the current note, available document numbers and attachment filenames. It ignores case and accents. It searches loaded records only, not all Business history or file contents. |
| Filters | Registro contains Venta, Gasto and Todos los tipos. Revisión, Adjunto, Moneda y monto, Contraparte, Categoría, Cuenta, Tipo de documento and Tipo fiscal share one panel. Phone uses the full-height sheet. Changes stage until Aplicar; dismissal discards the draft. Chips remove individual applied groups. Parent checkboxes support empty, mixed and checked states; a mixed click selects the visible options without losing hidden selections. |
| Amount range | Uses the shared MoneyInput. A currency is required first. Zero is valid, negative bounds are not. Canonical decimal strings preserve exact amounts. The shared parser limits significant whole digits to 15 and uses currency precision. Invalid length, precision or an inverted range prevents Apply and gets inline feedback. Invalid text is not silently converted to a valid bound. |
| Calendar | Typed locale dates replace native date popups. Format belongs in the placeholder; text below is for validation. Presets, range highlighting, hover preview, endpoint refinement and keyboard navigation share one range engine. Desktop has two months or three where space permits. Narrow dossiers use one. Phone uses a full-screen vertical calendar and bottom confirmation. The all-time requirement below is not yet connected to this local date control. |
| Financial cards | Appear automatically for Venta or Gasto. Sales show Facturado, Cobrado and Por cobrar. Expenses show Gastos, Pagado and Por pagar. Mixed Todos hides them. There is no Summary settings tab or visibility checkbox. Three compact cards show at most two currency rows each, with neutral text and theme-aware surfaces. A shared action for three or more currencies opens all currencies in the dossier or phone sheet. Currency remains a filter only inside Filtros. |
| Financial meaning | The preview derives from filtered loaded records and explicit synthetic settlement fixtures, before local pagination. It excludes ineligible amounts and exposes that qualification through an information control. Unknown is not zero. Currency amounts are never added together. Cards are read-only; amount drill-down is not implemented. Do not infer backend financial readiness from the fixture values. |
| Table | Default columns are Contraparte, Fecha, Monto, Moneda, Tipo, Categoría, Estado, Notas and Adjunto. Cuenta is hidden by default and available through settings. Dates are explicit. Amounts align right with tabular digits, never truncate, and have a separate display-currency column. Filter/export contracts use currency codes. Estado uses colored labels without dots; Listo is the short table label, while the overview retains Listos para exportar. |
| Table settings | Desktop has shared segmented controls for Columnas and Altura de filas. Optional columns use full-label checkbox targets. Contraparte is locked first; Monto and Moneda are required, adjacent by default, and independently movable. Six-dot handles support pointer drag and keyboard pickup with Space, arrows, Space to place and Escape to cancel. A picked-up column has a visible state and live announcement. Density supports 40, 48 and 56px rows. Settings apply immediately. The obsolete phone Summary-only gear is removed. |
| Sorting | Fecha, Monto and Contraparte headers share sorting with the phone control. Only the active header shows its sort arrow. Amount order is exact magnitude and requires one known currency across the filtered set. If that condition stops holding, the preview falls back visibly to newest-date order. Stable kind/ID ties prevent arbitrary reorder within the loaded set. |
| Notes | Current text only in the table, truncated with full text available through its editor. Empty cells show a dash at rest. A pencil appears on row hover or keyboard focus and remains visible for touch. The icon has the same direct-hover target treatment as attachment. The editor enforces 500 characters with the feedback-form counter pattern. Save updates local memory; Cancel discards. History belongs in Activity, not a second table affordance. |
| Attachments | Empty cells show a dash at rest, then a plus on row hover/focus or touch where editing is permitted. Unknown presence is not treated as missing. Existing linked evidence opens through its existing authorized path. The local attachment modal reuses the receipt drop zone, file picker/drop/paste, multi-file append, validation and byte deduplication. It has one divider and one full-width 8px-radius CTA, without redundant Cancel. Several files append without replacing existing evidence. Local files are not uploaded or durably linked and disappear on reload. Received-document linking remains unavailable. |
| Narrow list | Below 700px of table-container width, including beside a desktop dossier, a two-line list replaces the table. Identity leads; complete amount stays in the top-right slot; state and explicit date stay below. Touch actions remain accessible. A row opens the shared detail sheet, keeps the list mounted and restores source focus on close. |
| Pagination | The local loaded set is filtered and sorted before slicing. Default 25, with 50/100, bounded numbered links and first/previous/next/last controls. Counts describe the loaded matching set. Query, filter, sort, restored view or page-size changes reset page 1. Column and density edits do not. The local footer is not proof of server-wide coverage or stable concurrent browsing. |
| Saved views | Vistas contains both saved choices and Guardar vista. Local recipes capture search/kind, period, advanced filters and table preferences. They restore on page 1 and are cleared on reload. They save setup, not financial values or page 17. No metric catalogue, custom formulas, widget-order preference or summary-visibility preference is approved by this checkpoint. |
| Loading and recovery | Records skeleton follows visible columns/order/density, narrow rows and pagination footprint. Overview and toolbar keep their place. Shared shimmer respects reduced motion. Loading does not invent a count. Search empty state retains controls. API errors remain errors, not zero totals. |

Ready surfaces use the approved light sage `#B8D0BE` and dark counterpart, with
neutral content and selection edges. The reusable rules remain in
`.agent/designs/cuadrao-business-app/DESIGN.md`: shared segmented controls,
checkbox/radio targets, focus treatment, anchored desktop popovers, phone sheets,
dossier gradient, aligned money, validation placement, and the invite-style
single footer action. Do not replace these with browser-native controls when wiring.

### Backend reconciliation at the fetched integration head

Integration was fetched at `8c993ef76a0864261023d58846396d851a08c1f4`.
Its reporting contract supersedes the older statement that only period exports
exist in the backend. The current design client still uses its legacy reads and
local preview; it does not call the new reporting endpoints yet.

| Contract at integration | Current support | Frontend connection or remaining gap |
| --- | --- | --- |
| `POST /api/v1/business/reports/query` | `ReportRequest` has schema_version, filters, columns, sort, page and page_size. Filters include q, period, record_families, review_stages, has_document, currencies, amount_min/max, counterparties, categories, funding_sources, document_kinds and fiscal_classifications. `ReportAnswer` supplies items, matching_count, page/page_size/page_count, totals, fingerprint, captured_at, resolved_period, excluded_unknown_dates and option catalogues. | Replace loaded-array paging and fixture statuses/totals with this authorized result. Map canonical row identities/revisions, unresolved amounts, date_basis, blockers and coverage notes without fabricating facts. Preserve the separate overview Business/period query scope. |
| Search `filters.q` | Current integration matches counterparty, note, counterparty_key and fiscal_number, with a 200-character query bound. | Name/note/fiscal-number support exists. Attachment-filename and other document-reference coverage need reconciliation with the approved pilot names/notes/documents scope. Local preview filenames are not proof of server search coverage. No amount/date search expansion is requested. |
| Period | Integration supports all, custom, this_month, last_month and this_year with the Business calendar. All has no date bounds. | Expose genuine all-time in the client, including records older than a year, while requesting one bounded page. Map extra UI presets deliberately. Do not silently freeze a relative saved period or use the legacy year-2000 sentinel as all history. |
| Sort and recipe | `ReportRecipe` accepts only date_desc, filters and supported column order under schema_version 1. | Date ascending, amount in both directions and counterparty in both directions need allowlisted contract additions or an explicit product reconciliation. Map client column keys to report fields. Attachment presentation, required-column locks and row density are not all represented by this recipe. Do not send unsupported fields or silently lose preferences. Summary visibility/widget preferences no longer need a backend contract. |
| `POST /api/v1/business/reports/export` | Accepts report and expected_fingerprint. Returns a ZIP of filtered CSV/XLSX plus scope manifest, excluding originals. A changed report returns 409 business_report_changed. | Wire the export action to this scope and refresh/recovery behavior. The existing client `GET /business/exports?start&end&draft_id` remains period-based. It must not masquerade as filtered export. Explicit-ID selection export and original-evidence bundles need separate support before being exposed. |
| `/api/v1/business/report-views` | GET/POST and PATCH/DELETE by view ID exist. Recipes are person-and-Business scoped. Writes use idempotency keys; updates/deletes use expected_version. | Replace in-memory names/recipes with persisted views, reconcile fields and name limits, and handle stale versions and revoked access. Saved setup must not save calculated amounts. |
| Existing evidence reads/intake | Receipt detail/source and intake/review/confirm paths remain reusable, as documented in the earlier evidence matrix. | Supporting-file append is not new receipt intake. Public candidate eligibility/link/retry/unlink contracts remain unresolved here. Do not create a second activity to simulate attaching evidence. |
| Notes and Activity | The report exposes note as a read field. This checkpoint does not establish a durable editable-note command. | Backend owner must map or supply an authorized, version-checked 500-character edit command. Preserve author/time/history for Activity. Idempotency prevents duplicate retries; optimistic version checking prevents one editor silently overwriting another. These are distinct requirements. |
| Partial settlement | Reporting includes settlement_status and qualified totals, not proof of the proposed exact partial allocation projection. | Orchestrator owns the linked invoice/expense, payment-allocation and remaining-balance contract. Never derive paid/collected money from a binary status. Preserve one activity and its evidence/payments without counting invoice plus payment twice. Existing whole-document bank matching must not overwrite partial balances. |

The report's coverage notes explicitly include unavailable legal-cancellation
coverage, potentially unknown document subtypes and counterparty identity requiring
an explicit tax ID. Preserve those limits. A name match is not canonical identity;
an attachment is not fiscal verification; an authorized electronic issuer is not
proof that this workspace can issue. No hosted readiness is claimed here.

### Ownership and hosted acceptance required before release

The frontend lane owns visual patterns, responsive layout, keyboard/focus behavior,
mapping the approved contract, URL/return position, and client recovery states.
The orchestrator assigns backend owners and reconciles the existing reporting
contract before new API work. Engineering chooses query/index/storage details.
Changing approved product scope needs explicit resolution, not a quiet adapter fix.

Required acceptance cases are:

1. Search names, notes and agreed document identifiers across all authorized rows,
   including matches beyond page one. Reject access after membership revocation.
2. One query definition yields matching rows, count, totals and export across
   pages. Verify currency codes, exact amounts, unknowns, credits and coverage gaps.
   Scope overview counts separately by Business and period.
3. Reload a later numbered page; reset on filters/sort/page size; retain position
   for column/density edits. Return from a dossier to a stable row anchor. Handle
   a deleted anchor and removal of the final row on the final page explicitly.
4. Use all-time against several years and more than 100 records. Each client row
   response stays bounded. Counts/totals/export cover the full matching set.
5. Test equal dates, null dates, all approved sort directions and removal of the
   currency filter during amount order. Never compare DOP and USD as equal units.
6. Connect fingerprint/change detection to explicit refresh and invalid-page
   recovery. A fingerprint exists, but a passive notification mechanism is not
   proven by this preview. Do not silently insert rows or promise a frozen session.
7. Save/reload a view in the same person/Business scope. Switch Businesses and
   users, test revoked access and stale versions, and verify no preference leakage.
8. Export beyond one page with the approved fingerprint. A changed dataset gives
   a clear refresh path. Manifest records scope and capture time. Already generated
   output stays fixed. Do not silently retry with a different set.
9. Edit a note, reload, and inspect Activity. Concurrent edits preserve the losing
   draft and show a conflict. Same-key retry has one effect; changed-payload retry
   conflicts. Backend and frontend agree on the 500-character counting rule.
10. Append several attachments without replacing evidence or creating activity.
    Exercise duplicate bytes, retry, failed upload/source access, linked-document
    conflict, cross-Business denial and access revocation. Amount/payment state
    remains unchanged. New intake and existing-activity attachment stay distinct.
11. Verify a 100 invoice with 40 and 60 collections yields remaining balances of
    60 then 0, one invoice and two actual payments. Repeat/concurrent requests must
    not duplicate cash or over-allocate. Confirm historical-record compatibility
    under the separately approved settlement scope.
12. Run the integrated frontend on desktop and phone, light/dark and EN/ES. Cover
    keyboard-only interactions, touch targets, privacy masking, skeletons, no
    results, request failure, unknown totals, permission changes and recovery.

Local component tests, fixture values and browser viewport checks are design proof.
Hosted database, real persistence, cross-session and real-device acceptance remain
separate gates. The orchestrator must acknowledge this packet, record existing
versus missing support and add the outstanding requirements to its plan.

### Checkpoint verification and preserved work

The final UI change is commit `5524af078`, which removes the Summary setting and
derives visibility from record kind. Its state shape is now column order,
hidden columns, density and sort. Saved views no longer carry summary visibility.
The accompanying documentation commit is the checkpoint handed to the orchestrator.

`bun test __tests__/records-*.test.ts __tests__/records-*.test.tsx
__tests__/transacciones-*.test.ts __tests__/transacciones-*.test.tsx` passed all
137 tests across 13 files. Scoped ESLint and `git diff --check` passed. Two older
screen tests were updated to assert the approved cards/settings instead of the
removed summary text and checkbox. Previous whole-project typecheck limitations
remain recorded above; this is not a claim of fresh whole-repository CI.

The existing port 4387 browser preview confirmed the two remaining desktop
settings segments, automatic expense cards, the 390px phone layout and absence
of the obsolete phone settings shortcut. Component tests also cover automatic
Sales/Expenses/Todos transitions and currency dossier focus restoration on both
widths. Earlier light/dark and EN/ES evidence remains historical evidence at its
named revisions, not a new full-matrix run at this checkpoint.

No backend file, service, migration, integration flag or hosted state changed.
The unrelated untracked design-recovery and design-startup directories remain
untouched and are excluded from the commit. The existing preview server remains
available; no extra server was started.
