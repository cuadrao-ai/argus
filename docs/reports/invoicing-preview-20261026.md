# Facturación: design and behavior record

Status: **draft for the user's final review; not an approved checkpoint**.
Updated: 26 October 2026. This consolidated guide replaces the chronological notes
previously in this file. The current implementation takes precedence over those
older descriptions, especially for partial draft saving and the expanded editor.

Code baseline: `22b12a6b74bbc66c5bf005b2f63318554861235a` on
`codex/frontend-design-after-home-20261024`.

- [Backend requirements and acceptance handoff](../handoffs/invoicing-design-checkpoint-20261026.md)
- [Shared Business design rules](../../.agent/designs/cuadrao-business-app/DESIGN.md)
- Local workspace: `http://127.0.0.1:4387/biz?view=invoicing`
- Seeded workspace: `http://127.0.0.1:4387/biz?invoicePreview=seeded&view=invoicing`

## 1. What is real in this preview

The interactions are implemented frontend behavior. Invoice, customer, payment,
correction and schedule data are synthetic and session-local. They are scoped by
selected Business and fixture variant in a module-level store. Closing and
reopening the surface retains saved local records; reload or module replacement
resets that store. No durable invoice/customer/payment/schedule API is connected.
Existing Business context supplies the selected Business identity.

Fiscal status fixtures, payment calculations and correction reducers demonstrate
states; they do not establish hosted issuance, delivery, collection or fiscal
acceptance. A polished screen is not proof of those services.

## 2. Workspace and navigation

The surface heading aligns with Registros. Facturas, Clientes and Programadas use
the shared workspace segmented control. Inside Facturas, an underline tab bar
selects Todas, Borradores, Por cobrar, Cobradas or Anuladas. Fiscal processing,
delivery and collection are separate facts, not interchangeable tab labels.

The order in Facturas is:

1. Workspace switch and invoice-stage tabs.
2. Search, period, filters, Crear factura and Ajustes.
3. Financial cards, only in Todas when there are financial summary values.
4. Invoice table or compact phone list.
5. Pagination outside the table card.

A row opens its dossier without replacing the list. Creation opens the expanded
editor dossier immediately. Expanding/collapsing preserves the same draft.

### Scope that a screenshot does not reveal

| Element | Current local scope |
| --- | --- |
| Stage-tab counts | Selected Business and page period; not narrowed by search or currency |
| Rows and result count | Period, selected stage, search, currency and overdue shortcut |
| Financial cards | Same filtered result set, across all its pages; eligible issued invoices only |
| Pagination | Slices local results; does not change the financial total |
| Customers and schedules | Selected Business and local fixture session |

Search matches customer name, invoice reference and invoice notes. Command-K
focuses this surface's search when an editor/dossier is not open. It does not
search every field or remote records. Currency lives inside Filtros; overdue is a
removable shortcut in the collection view. The period control reuses the custom
calendar, including an unbounded local Todo selection.

Ajustes offers row density and sorting. Customer and issue-date headers also sort.
It is not the full Registros column picker, saved-view manager or export menu.
There is no mixed-currency amount sort.

## 3. Financial cards and table

Todas shows Facturado, Cobrado and Por cobrar below the controls. Other stage tabs
hide the cards. These are summaries, not stage selectors or clickable drilldowns.
Search and filters update them; changing the page does not.

They reuse the compact Registros card family: rounded neutral/sage/cream surfaces,
neutral text, an icon, short label, prominent amount and dark-theme equivalents.
Each card shows at most two currencies, in the same order across the three cards.
Currencies are never added together. Above two, one shared breakdown action opens
the existing dossier, with all currencies grouped separately and the three
amounts inside each group. This action does not apply a currency filter. Closing
returns focus to its trigger. Privacy masking applies to amounts.

Facturado currently means original issued total plus confirmed debit adjustments
minus confirmed credits. Cobrado is allocated payments. Por cobrar is the
remaining balance. Drafts and uncertain issuance do not become confirmed money.
The model counts exclusions, but this component does not yet expose their
explanation. That integration gap is explicitly carried in the handoff.

A known empty filtered set for a selected currency can show 0/0/0 in that currency.
This must never stand in for loading, an unavailable amount or a failed request.
With no summary currencies otherwise, the summary is absent.

The desktop invoice table separates Moneda from numeric Total and Por cobrar.
One currency cell applies to both amounts in that row; numbers are right-aligned
with tabular figures. Currency display follows Registros, while future exports
must carry the currency code. Dates are explicit. Missing or inapplicable values
use a dash; unknown issuance balance is not a fabricated zero.

Phone uses compact identity/value/state rows rather than a shrunken desktop table.
Amounts keep their currency context and due dates retain a descriptive label.

Pagination now matches Registros: count on the left, `25 por página` in the center,
first/previous, a bounded page-number range, next/last on the right. Sizes are
25/50/100. Query changes reset the page; density does not. This is local slicing,
not proof of server-side pagination or counts.

## 4. Empty states and setup

The first-use Todas state shows three setup cards above the invoice artwork:
Business details, customer creation and first invoice. Each opens the relevant
existing setting or workflow. The first saved local draft replaces this cold start
with the working list. Filters with no matches show a clear-filter recovery, not
an invitation to set up the Business again.

Setup progress is an approved requirement, not connected persistence: checkmarks
must derive from valid saved facts automatically. Visiting a card is not completion.
Automatic progress tracking does not mean every form silently autosaves. See the
handoff for the exact backend requirement.

Other empty stages have contextual invoice artwork and copy; Clientes uses the
customer illustration and Programadas the calendar illustration. There is no bell
artwork borrowed from notifications. Art is decorative and never implies approval.

## 5. Invoice creation: one draft, four steps

Desktop opens a wide dossier with the current form on the left, a vertical divider,
and a longer live invoice on the right. The footer remains anchored. Long content
may scroll; the editor does not present all four sections as one long form.
Phone uses the same draft in the full sheet with Editar/Vista previa.

### Step 1: ¿Para quién es esta factura?

The first customer-name field is both the existing-customer picker and the entry
point for a new customer. It is not duplicated after selection. Cold start shows
that field and its information notice only. Selecting a customer fills the remaining
fields; adding one reveals those fields in place. The notice disappears once its
purpose is satisfied. Changing customer does not discard item or terms work.

Email, tax identification and address use shared labels, placeholders, blur/error
feedback and reserved validation space. Customer limits are name 120, email 254,
address 240 and tax ID 120 characters. Domestic numeric IDs require 9 or 11 digits,
excluding an all-zero value; spaces and hyphens are accepted for formatting. This
is format validation, not registry verification. E31 requires domestic identification.
In the document, identification is labeled `RNC:` or `CED:` with a colon.

The document type belongs to the invoice's terms, not the customer's metadata.
Saving a valid new customer can populate the local customer registry. Saving an
incomplete invoice draft must not create an invalid customer record.

### Step 2: Detalles / Details

Currency sits beside the heading. Each product has Description, a compact Quantity,
Price and its own delete action. Tax and fixed line discount sit below. Adding a
product collapses the prior item into a readable summary and expands the new one.
Clicking that summary reopens it. Validation opens the affected item instead of
hiding its error. At least one item remains; the local maximum is 50.

Description is bounded to 160 characters. Numeric entry rejects invalid formats,
uses decimal precision limits and formats valid money on blur. The common money
parser accepts up to seven integer digits and two fractional digits; individual
quantity/tax controls have tighter bounds. Discounts cannot exceed that line's
quantity times price. Each discount reduces its line before tax. Exact scaled
arithmetic drives the form, document and summary, but fiscal tax/rounding acceptance
still requires backend verification.

Customer-visible invoice notes are separate from email text and use the shared
500-character counter. The action reads Añadir producto, not Añadir concepto.

### Step 3: Condiciones

Invoice document type, issue date, due date and payment instructions live here.
Issue and due dates are side by side on desktop. The custom calendar allows typed
dates and inline validation, without a browser-native calendar layered on top.
Due-date shortcuts are Today, +7 days, +15 days and +1 month, relative to today.
The month shortcut clamps to the last valid day. Issue-date shortcuts are Today
and Yesterday.
Dates must be valid and ordered. Payment instructions are bounded to 500 characters.
Provider numbering and actual fiscal eligibility remain server responsibilities.

### Step 4: Review and email preparation

A clear review heading leads into To, optional Cc and Message. Quiet links return
to Customer, Details or Terms without losing the draft. The right preview uses a
real Factura/Correo tab bar with keyboard navigation, not a segmented control.

To starts from the customer snapshot. Cc accepts up to five comma- or
semicolon-separated valid addresses. Message is limited to 500 characters and is
separate from the note printed on the invoice. Email preview updates from the same
draft. Its illustrated PDF tile is not an actual generated attachment.

The current primary action saves email preparation locally. It does not issue,
send or mark delivery successful. The UI states that boundary. Do not describe it
as the reference screenshot's working Send button.

### Actions and document details

- Next validates only the current step; Back retains all inputs.
- Save draft allows incomplete data, including incomplete email preparation.
  Issuance and preparation have their own validation gates.
- The primary action uses the collaborator-invite button shape. Quiet Save draft
  and Back actions avoid a second competing primary action or redundant Cancel.
- Closing a changed draft offers save/discard. Reload warns about unsaved work,
  but it does not make the session store durable.
- The preview updates as the form changes. Its customer/date regions have a middle
  divider and a horizontal divider before products. Footer branding is localized.
- Rounded corner brackets frame the active document section without covering text.
  They squeeze gently three times on section entry and respect reduced motion.
  They are editing aids, absent from saved/printed output.
- Copy refresh support does not amount to recovery across every code hot reload.

## 6. Existing invoice dossier

The dossier keeps the invoice, customer snapshot, payment allocations, corrections,
delivery preparation and local history connected. Browser print/customer HTML is
available separately from official fiscal files. Blocked popups are handled.
Official XML, official PDF and verification slots remain unavailable in this preview.

The local payment model supports basic partial payments: 40 against 100 leaves 60;
60 more leaves 0. Wrong currency, overpayment, draft payment and duplicate payment
IDs are rejected. These actions record illustrative allocations, not bank transfers.

Issuance, fiscal processing, delivery and settlement remain separate. Sample
issuance enters processing; there is no timer that declares fiscal acceptance.
Uncertain issuance cannot simply be issued again. Local history is not a durable
actor-attributed audit log.

Corrections preserve the original invoice. Full cancellation and partial credit
use distinct paths from debit adjustment. Requests remain pending until an outcome
is resolved; failed requests preserve their data and allow a new attempt. Duplicate
or stale resolution cannot apply the same adjustment twice. Only confirmed full
cancellation enters Anuladas. A full-value partial credit is not automatically a
cancellation. Payments remain linked and a customer credit is not an automatic refund.
These are local model behaviors, not provider calls.

## 7. Clientes and Programadas

Clientes is a desktop table, not a gallery of contact cards. It shows identity,
last activity, last invoice, last payment and next planned draft. Creation date is
available in settings and hidden by default. Search, active/archive access and the
customer dossier support add, edit, archive confirmation and restore locally.
Customer edits do not rewrite invoice snapshots. Archived customers remain in
history but are excluded from new-customer selection. Customer links use IDs, not
name matching. A company/person relationship is not inferred from similar names.

Programadas creates a separate template copy from a saved draft, tied to an active
customer. Weekly, monthly and yearly schedules preserve month-end/leap-year
anchors. Users can edit, pause and resume. Planned dates are not claims that a run
occurred. Creating a draft is the default mode. Automatic issuance is visibly
unavailable until real readiness exists and must eventually require explicit opt-in.
No worker, timer, billing charge or hosted recurring execution is connected.

## 8. Reuse and remaining frontend gaps

Reuse includes AdaptivePanel, FormField/useFieldChecks, custom calendars,
SegmentedControl for workspace switching, ToolbarPicker, shared button classes,
identity marks, money formatting, the Records summary card styles and pagination
page-link helpers. The theme-aware dossier gradient stays in the shared panel.

This surface does not yet implement full Registros parity: saved views, column
configuration, selection/export, URL-based query restoration, request loading/error
skeletons and all sidebar-navigation unsaved-edit guards remain separate work.
Do not infer these from visual similarity. Customer HTML does not yet incorporate
every saved Business legal/contact field. Generated/printed output requires its own
verification before hosted acceptance.

## 9. Reproducible local review

Keep the existing server. Omit `invoicePreview` for a cold start; use `seeded` for
the four-record example. The query parameter selects synthetic state, not a provider
or live account. Other explicit values exercise `correction-pending`,
`correction-failed`, `correction-confirmed`, `partial-confirmed`, `credit-balance`,
`debit-confirmed`, and fiscal `processing`, `accepted`, `observations`, `rejected`,
`failed`, `uncertain` prefixed with `fiscal-`. Fixture dates move with the local day.

Useful review actions beyond screenshots: open a row; save/reopen an incomplete
draft; use the customer picker with arrows/Enter/Escape; add a second item and reopen
the collapsed first one; paste invalid money; switch the review's invoice/email
tabs with arrow keys; close a changed draft; archive/restore a customer; pause a
schedule; change page size; select a currency with no matching invoices.

Source map: `InvoicingPreview` owns workspace state and query scope; `InvoiceEditor`
owns the step flow; `InvoiceDocument` and `InvoiceEmailPreview` render the same
snapshot; `InvoiceDossier` and `InvoiceCorrections` expose record actions;
`InvoiceResultsSummary` and `invoice-results-summary` own the metric presentation
and aggregation. Customer and schedule components use their respective local models.
All are under `web/components/business-app/invoicing/`.

## 10. Evidence and review boundary

This document was reconciled against the code baseline above. The prior local
sweep at `d172de300` recorded desktop/phone, EN/ES and light/dark checks and partial
draft recovery. The subsequent `22b12a6b7` change aligned pagination and received a
focused desktop check. Those are dated local checks, not a fresh complete browser
sweep at this documentation revision.

Repository-wide TypeScript was previously not clean because of unrelated test and
Records typing issues. No clean full build, hosted verification, fiscal activation,
production issuing or delivery acceptance is claimed. Fresh focused test results
for this review are recorded in the handoff. User review is still required before
sending anything to the orchestrator.
