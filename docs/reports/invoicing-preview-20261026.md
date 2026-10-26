# Invoicing connected design preview, 2026-10-26

## Scope and entry

Frontend-only first pass on `codex/frontend-design-after-home-20261024`, following the frozen Registros checkpoint `22aab17dd8f3258e4692f13aa002509b9fd85b73`. Open `/biz?view=invoicing` on the existing local server. Desktop navigation includes Facturación only in development with mock authentication. Phone verification uses the direct URL; the shared phone navigation remains unchanged.

No backend, provider activation, real issuance, email sending, hosted access, push or checkpoint handoff is included.

## Connected behavior

- Workspace uses Todas, Borradores, Por cobrar, Cobradas and Anuladas stage tabs. Counts follow the selected Business and page period. The overdue shortcut belongs inside Por cobrar. Tabs support arrow keys, Home and End, and link to their results panel. A true first-use empty state offers one Create invoice action. Filtered empty results offer clear filters.
- Search matches customer name, invoice reference and notes in the local fixture set. Command-K focuses this search when no editor or dossier is open.
- A compact filter-aware adjusted-total/collected/outstanding summary use issued invoices only, exclude drafts and uncertain issuance, and preserve separate currencies. Pagination changes displayed rows, not totals.
- Date controls, currency filtering, customer/date sorting, density and numbered pagination use the established workspace patterns. Page sizes are 25, 50 and 100; relevant query changes reset the page.
- Desktop rows open the connected dossier. Below the table container breakpoint the same records become a phone list with aligned amounts and explicit due-date text.
- Draft editor opens in the shared right dossier while the workspace remains mounted. The normal editor has one column. The header expansion control reveals the live invoice preview beside it without remounting the draft. Expansion keeps the normal drawer-space claim, so the workspace is not squeezed to the expanded width. Phones use Editar and Vista previa inside the same full sheet. The editor retains customer entry, items, exact quantity/price/tax, currency, calendar dates, terms, customer-visible notes and payment instructions.
- Shared inline validation checks required fields, valid date ordering, email format, positive total and bounded decimals. Save focuses the first invalid field. Closing an edited draft offers save/discard; reload warns about unsaved changes.
- Save/reopen retains the same local invoice identity. Sample issuance is explicit and separate from delivery. Delivery preparation saves channel/recipient without claiming a message was sent or a public link exists.
- Payments include amount, original currency, date, method and reference. Partial payments reduce the same invoice balance; they are not extra sales. Overpayment, currency mismatch, draft payment and repeated payment ID are rejected in the local model.
- Uncertain issuance cannot be blindly repeated. A failed-delivery example offers review/preparation. Actual status recovery requires backend checks.
- Customer HTML uses the selected Business name and saved identity image, customer details, invoice items, totals, due date and payment instructions. Issued invoices also show collected and outstanding amounts. Browser print/save-as-PDF is an alternative action, not a generated or hosted PDF service. Blocked popups show a message.
- Concise local history shows saved/issued/prepared facts and linked payments. It does not invent actor identities or precise event timestamps.

## Reused components and patterns

Actual reuse: `AdaptivePanel`, `FormField`/`useFieldChecks`, `SegmentedControl`, `ToolbarPicker`, `RecordsDatePreview`, pagination page-link helper, shared button/field classes, money formatting, `SavedIdentityMark`, sidebar navigation button. Dossier gradient and phone-sheet behavior come from the shared panel.

Invoice-specific components include `InvoicingPreview`, `InvoiceEditor`, `InvoiceDossier`, `InvoiceDocument`, `InvoiceStageTabs`, `InvoiceCorrections`, `InvoiceDateField`, the local invoice model/reducer and scoped CSS. `InvoiceDateField` reuses the shared calendar. Existing RecordRow-specific table code is unchanged. The shared panel extension is opt-in. Existing consumers keep their width and controls; phone sheets do not receive a desktop expansion control.

## Preview truth and remaining frontend work

All invoice data is synthetic, scoped by selected Business and explicit fixture variant in memory. The default starts empty. Changes survive closing/reopening the local surface but reset on reload or module refresh. No invoice/customer/payment API is wired by this work. Existing Business context supplies the selected identity.

This is a connected first pass, not full Registros feature parity. Follow-up design/implementation includes named saved views, column configuration, URL restoration, request loading/failure skeletons, selection/export, phone navigation placement and guarding unsaved edits when navigating through the shared sidebar. Dates now reuse the shared calendar and DD/MM/YYYY entry. Customer document currently reuses Business name/image, not every profile contact/legal field. Printed output and actual PDF generation still need dedicated verification. Do not describe these as completed features.

## Backend dependencies for a later authorized checkpoint

1. One authoritative Business-scoped customer/invoice/item model, durable draft persistence, version checks for concurrent editing and idempotent commands. Basic customer identity must not become name-based matching.
2. Issuer readiness, fiscal numbering, applicable tax rules and fiscal acceptance are server-owned. Uncertain issuance needs reliable reconciliation before retry. Do not infer sent, viewed or paid from issuance.
3. Delivery needs actual email outcomes and secure customer links with explicit access, expiry/revocation and public-document rules. A recipient preview must not expose internal notes or broader Business data. PDF generation/versioning and legal issuer details need their own contract.
4. Payments require durable allocations linked to the invoice, exact amounts, original currency, idempotency and concurrency protection. The local correction model does not establish backend correction or refund policy. Instructions are not payment processing.
5. Rows, counts, totals, pagination and eventual exports must share one authorized query definition. Totals exclude unconfirmed issuance and never sum currencies. Direct numbered navigation, deterministic ordering and changing-data recovery follow the agreed Registros contract.
6. Activity needs real actor/event timestamps and links, not UI-created audit claims. Issued-document branding/legal identity must have an explicit snapshot policy.
7. Acceptance: create/save/reload same draft; reject invalid data; issue once; recover uncertain response safely; prepare/send without conflating statuses; payment40 on invoice100 leaves60; payment60 leaves0; repeated request does not duplicate allocation; reject unauthorized Business access; preserve mixed-currency meaning; independently verify hosted recipient access and PDF output.

Do not send this document as a checkpoint until the user authorizes that checkpoint. Coordinate the eventual contract with the existing customer/invoice/payment-allocation milestone rather than adding parallel persistence.

## Verification

- 30 focused tests pass across `invoicing-preview.test.ts`, `invoicing-panel.dom.test.tsx` and `business-date-picker.dom.test.tsx`. They cover save/issue/preparation/40+60 payments, exact arithmetic, correction outcomes, retry/idempotency, original evidence preservation, fiscal types/states, shared-panel compatibility and date validation accessibility.
- Focused ESLint and `git diff --check` pass.
- Current browser checks on the existing server covered desktop at 1440px and phone at 389px, light/dark appearances and EN/ES copy. Verified cold-start artwork, expansion without losing draft fields, phone editor/preview switching without horizontal overflow, save/issue, partial and final payments, confirmed cancellation and failed-correction retry without changing the original balance. Required date validation retains its accessible error after invalid text is cleared.
- Full workspace TypeScript is not clean: pre-existing errors include `foundation/home-greeting.ts` timer typing and `transacciones/RecordsResultsSummary.tsx` nullable string, plus unrelated test declarations. No new invoice-file errors appeared in the filtered check. No full-build or hosted acceptance claim.
- Current evidence outside Git: `/private/tmp/invoicing-cold-start-desktop-es.png`, `/private/tmp/invoicing-cold-start-desktop-light.png`, `/private/tmp/invoicing-cold-start-phone-light.png`, `/private/tmp/invoicing-cold-start-phone-dark.png`.

## Fiscal and correction first pass

E32 is the default document type. E31 requires a customer RNC or identity number in the editor. The local check validates 9 or 11 digits only; it does not establish registry identity or legal eligibility. Tax entry remains illustrative.

Fiscal state is separate from invoice issuance, delivery and payment. The local model names processing, accepted, accepted with observations, rejected, failed and uncertain outcomes. Sample issuance enters processing. Repeating issuance on an issued or uncertain invoice does nothing. No timer fabricates an accepted result.

The dossier reserves a section for official XML, official PDF and fiscal verification. They are unavailable in this frontend preview. The printable customer HTML is separate and does not become an official fiscal PDF. Issuing readiness is unknown and links to the existing Business details settings. It does not introduce a setup form in Facturación.

Each correction keeps its ID, kind, reason, exact amount and numbered attempt history. E34 full cancellation and partial credit are distinct from E33 debit adjustments. Preparing a request leaves it pending locally. Failed requests retain their fields and can retry with the same correction ID and a new attempt number. Stale or duplicate resolutions cannot apply a second adjustment. Only a confirmed full cancellation enters Anuladas. A full cancellation uses the remaining creditable total, not the unpaid balance. A partial credit equal to the total remains credited, not void; without payments it appears under Todas, not Cobradas.

Original items, total, issuance, delivery and payment evidence remain intact. Confirmed credits reduce the current balance; confirmed debits increase it. A credit exceeding the unpaid amount creates an explicit customer credit balance. It does not infer a refund or erase a payment. Pending and failed outcomes cannot change balances. Only one correction may be pending per invoice.

Backend work must supply authoritative fiscal outcomes, correction eligibility, reference relationships, idempotency keys, invoice versions and concurrency handling. It must also define readiness/certificate checks, numbering, tax rules, official evidence availability and delivery ownership. Re-preparing or re-sending must reuse the existing invoice ID. No requests or official asset URLs are invented here.

## Deterministic review fixtures

Open `/biz?view=invoicing` for the default empty workspace. Add `&invoicePreview=seeded` for the preserved sample records. Each explicit variant has separate local session state; closing and reopening the same Business and variant retains its records. Reload resets the preview. There are no product-facing fixture controls.

The following variants modify invoice M-002 only:

| `invoicePreview` value | State |
| --- | --- |
| `correction-pending` | Full cancellation awaits confirmation; original balance remains |
| `correction-failed` | Full cancellation failed; retry retains its ID |
| `correction-confirmed` | Full cancellation is confirmed and appears in Anuladas |
| `partial-confirmed` | Confirmed partial credit reduces the balance without voiding |
| `credit-balance` | Payment plus confirmed credit leaves a customer credit balance |
| `debit-confirmed` | Confirmed debit raises the current total and balance |
| `fiscal-processing` | Processing |
| `fiscal-accepted` | Accepted |
| `fiscal-observations` | Accepted with observations |
| `fiscal-rejected` | Rejected |
| `fiscal-failed` | Failed |
| `fiscal-uncertain` | Uncertain |

Outcome resolution is exposed only to reducer tests and these deterministic fixtures. The customer-facing correction form cannot confirm or fail its own request.

## Current verification limits

The final focused suite has 30 passing tests. Focused ESLint and `git diff --check` also passed. An independent read-only review identified competing date-field accessibility updates; optional invalid/description props now give the shared DatePicker one owner for those attributes. A regression test failed before the fix and passes afterward. The reviewer confirmed the fix and reported no further findings. A filtered TypeScript check found no invoice-component or shared-panel errors. The repository-wide check still fails on existing timer/nullability errors and test declarations. The DOM environment cannot parse CSS `min()` widths; live desktop/phone review verified the actual layout. Expansion is immediate and does not animate layout properties. No backend or hosted acceptance is claimed.

## Cold-start illustration

Asset: `web/public/images/invoicing/first-invoice.png`. Generated with the built-in image-generation tool using the existing confirmation envelope and notification bell as style references. The transparent image replaces the simple outlined paper illustration and is decorative, with no paid or accepted marker.

Prompt used:

> Create one new invoice illustration for Cuadrao's empty invoicing screen, matching these two reference illustrations as a cohesive asset family. References are style guides only, not subjects to duplicate. A single upright cream invoice sheet with a softly folded corner, slight three-quarter tilt, softly rounded silhouette, a few deep forest-green abstract item lines and a separated total line, subtle sage-green thickness/shading and one small lime accent tab. Sculpted matte paper, gentle 3D volume and fine soft texture like the bell and envelope. Quiet, polished, friendly, legible at 150px. No letters, numbers, currency symbols, checkmark, paid stamp, logos, surrounding objects, glow cloud, or background card. Centered composition with modest breathing room, fully transparent alpha background. This is decorative blank invoice artwork, not proof of payment or acceptance. Save the resulting asset and return its local path.
