# Invoicing connected design preview — 2026-10-26

## Scope and entry

Frontend-only first pass on `codex/frontend-design-after-home-20261024`, following the frozen Registros checkpoint `22aab17dd8f3258e4692f13aa002509b9fd85b73`. Open `/biz?view=invoicing` on the existing local server. Desktop navigation includes Facturación only in development with mock authentication. Phone verification uses the direct URL; the shared phone navigation remains unchanged.

No backend, provider activation, real issuance, email sending, hosted access, push or checkpoint handoff is included.

## Connected behavior

- Workspace: draft, outstanding, overdue and paid preset views. Overdue is a subset of outstanding. Overview cards follow selected Business and page period, independently of text/currency filters; clicking again clears the selected view.
- Search matches customer name, invoice reference and notes in the local fixture set. Command-K focuses this search when no editor or dossier is open.
- Filter-aware invoiced/collected/outstanding cards use issued invoices only, exclude drafts and uncertain issuance, and preserve separate currencies. Pagination changes displayed rows, not totals.
- Date controls, currency filtering, customer/date sorting, density and numbered pagination use the established workspace patterns. Page sizes are 25, 50 and 100; relevant query changes reset the page.
- Desktop rows open the connected dossier. Below the table container breakpoint the same records become a phone list with aligned amounts and explicit due-date text.
- Draft editor: customer selection/basic entry, items, quantity, price, tax percentage, currency, dates, terms, customer-visible notes and payment instructions. Desktop live preview and phone preview share one invoice document.
- Shared inline validation checks required fields, valid date ordering, email format, positive total and bounded decimals. Save focuses the first invalid field. Back offers save/discard; reload warns about unsaved changes.
- Save/reopen retains the same local invoice identity. Sample issuance is explicit and separate from delivery. Delivery preparation saves channel/recipient without claiming a message was sent or a public link exists.
- Payments include amount, original currency, date, method and reference. Partial payments reduce the same invoice balance; they are not extra sales. Overpayment, currency mismatch, draft payment and repeated payment ID are rejected in the local model.
- Uncertain issuance cannot be blindly repeated. A failed-delivery example offers review/preparation. Actual status recovery requires backend checks.
- Customer HTML uses the selected Business name and saved identity image, customer details, invoice items, totals, due date and payment instructions. Issued invoices also show collected and outstanding amounts. Browser print/save-as-PDF is an alternative action, not a generated or hosted PDF service. Blocked popups show a message.
- Concise local history shows saved/issued/prepared facts and linked payments. It does not invent actor identities or precise event timestamps.

## Reused components and patterns

Actual reuse: `AdaptivePanel`, `FormField`/`useFieldChecks`, `SegmentedControl`, `ToolbarPicker`, `RecordsDatePreview`, `RecordsSummaryCards`, pagination page-link helper, shared button/field classes, money formatting, `SavedIdentityMark`, sidebar navigation button, and Registros overview styles. Dossier gradient and phone-sheet behavior come from the shared panel.

New invoice-specific components: `InvoicingPreview`, `InvoiceEditor`, `InvoiceDossier`, `InvoiceDocument`, local invoice model/reducer and scoped CSS. Existing RecordRow-specific table code is unchanged. Shared component extensions need ownership coordination.

## Preview truth and remaining frontend work

All invoice data is synthetic, scoped by selected Business in memory. Changes survive closing/reopening the local surface but reset on reload or module refresh. No invoice/customer/payment API is wired by this work. Existing Business context supplies the selected identity.

This is a connected first pass, not full Registros feature parity. Follow-up design/implementation includes named saved views, column configuration, URL restoration, request loading/failure skeletons, selection/export, phone navigation placement and guarding unsaved edits when navigating through the shared sidebar. Draft dates are typed ISO dates; reuse of the richer calendar needs a focused adaptation. Customer document currently reuses Business name/image, not every profile contact/legal field. Printed output and actual PDF generation still need dedicated verification. Do not describe these as completed features.

## Backend dependencies for a later authorized checkpoint

1. One authoritative Business-scoped customer/invoice/item model, durable draft persistence, version checks for concurrent editing and idempotent commands. Basic customer identity must not become name-based matching.
2. Issuer readiness, fiscal numbering, applicable tax rules and fiscal acceptance are server-owned. Uncertain issuance needs reliable reconciliation before retry. Do not infer sent, viewed or paid from issuance.
3. Delivery needs actual email outcomes and secure customer links with explicit access, expiry/revocation and public-document rules. A recipient preview must not expose internal notes or broader Business data. PDF generation/versioning and legal issuer details need their own contract.
4. Payments require durable allocations linked to the invoice, exact amounts, original currency, idempotency and concurrency protection. Define correction/refund/overpayment policy before exposing those actions. Instructions are not payment processing.
5. Rows, counts, totals, pagination and eventual exports must share one authorized query definition. Totals exclude unconfirmed issuance and never sum currencies. Direct numbered navigation, deterministic ordering and changing-data recovery follow the agreed Registros contract.
6. Activity needs real actor/event timestamps and links, not UI-created audit claims. Issued-document branding/legal identity must have an explicit snapshot policy.
7. Acceptance: create/save/reload same draft; reject invalid data; issue once; recover uncertain response safely; prepare/send without conflating statuses; payment40 on invoice100 leaves60; payment60 leaves0; repeated request does not duplicate allocation; reject unauthorized Business access; preserve mixed-currency meaning; independently verify hosted recipient access and PDF output.

Do not send this document as a checkpoint until the user authorizes that checkpoint. Coordinate the eventual contract with the existing customer/invoice/payment-allocation milestone rather than adding parallel persistence.

## Verification

- Four focused model tests: connected save/issue/preparation/40+60 payments and duplicate protection; rejected invalid transitions; bounded values/date ordering/overdue scope; exact line rounding and maximum supported multiplication.
- Focused ESLint and `git diff --check` pass.
- Browser checks on existing server: desktop and 390px phone, light/dark, EN/ES. Verified save/reopen, customer preview, email preparation, partial/final payment, validation and save/discard behavior.
- Full workspace TypeScript is not clean: pre-existing errors include `foundation/home-greeting.ts` timer typing and `transacciones/RecordsResultsSummary.tsx` nullable string, plus unrelated test declarations. No new invoice-file errors appeared in the filtered check. No full-build or hosted acceptance claim.
- Evidence outside Git: `/private/tmp/invoicing-desktop-light.png`, `/private/tmp/invoicing-phone-dark.png`.
