# Registros desktop filter design, October 25, 2026

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

### Compact result cards and summary choices (2026-10-25)

Compact neutral cards replace the results strip. Sales and expenses are selected by default; the fixed catalogue also offers record count and records without a linked backing file. Each money card stacks currencies, keeps the privacy mask, and names its own personal, unconfirmed or unavailable exclusions. Count, review and overall exclusions remain a quiet supporting line. All amounts still use the existing exact summary over loaded results before pagination.

Personalizar resumen opens the shared desktop popover or phone sheet. One ordered local selection owns the cards. Checkboxes, Restore defaults, pointer/keyboard reorder and phone move buttons edit a draft; Apply commits it. Close or Escape discards it. During a keyboard grab, the first Escape restores the previous draft order and leaves the picker open. An empty selection keeps the customize action available.

Without-document counts only `hasProof === false`. A null value is unknown and is qualified separately; if every result has unknown file information, the metric shows unavailable rather than zero. This is linked-file presence only, not fiscal verification, approval or document validity.

The four supported choices are local memory only. They do not write `/me`, change records or queries, persist across refresh, or become part of a named saved view in this slice. Each named view must eventually save the selected metrics and their order alongside its filters and columns. The later backend handoff must define the preference contract and authoritative per-metric eligibility and totals. Hosted acceptance must prove Business isolation, separate currencies, unknown versus missing files, filter-wide totals across pages, preference recovery, and privacy masking. No hosted acceptance or new backend support is claimed here.

Focused checks cover draft/apply/discard, empty selection recovery, keyboard and pointer reorder, phone touch reorder, unknown file information, per-kind exclusion arithmetic and privacy hooks. Existing pagination and search/kind integration tests keep their original result scope.
