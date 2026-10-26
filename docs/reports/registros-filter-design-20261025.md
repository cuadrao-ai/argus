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
