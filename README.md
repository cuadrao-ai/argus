# Cuadrao

Cuadrao helps small businesses in the Dominican Republic and their accountants turn receipts and invoices into reviewed records and the 606/607 reports.

The personal iOS app is archived at tag `archive/ios-personal-2026-10-30` and branch `archive/ios-personal`.

## How it works

1. **Bring documents in.** In this order of priority:
   - Upload receipts and invoices from the app.
   - Forward them by email to the business's own receipts address.
   - Send them by WhatsApp.
2. **Read.** Cuadrao extracts the merchant, date, amounts, NCF and RNC from each document.
3. **Review and approve.** The owner or the accountant checks each record, fixes what is wrong, and approves it. A possible duplicate blocks approval until someone resolves it.
4. **Follow up.** Each record keeps a status, so the owner can see what is still open:
   - A purchase is *pendiente* or *pagado*.
   - A sale is *pendiente* or *cobrado*.
   - The month-close view lists the sales still to collect and the ITBIS on sales already collected.
5. **Export.** Approved records produce the 606 and 607 reports.

## Currencies

Amounts are stored in the currency of the document and shown by currency. When a month holds more than one currency, a currency menu switches the figures. The DGII reports declare pesos (DOP) only. Foreign-currency lines are kept, marked "Moneda extranjera: pendiente de tasa", and are not converted.

## Where the owner starts

The app opens on Inicio, which counts what is waiting for review and flags the ones with problems. Tapping it opens the Bandeja, where documents wait to be read, reviewed or fixed. Registros holds the approved records. Mail from a sender that isn't on the business's list is kept apart in Remitentes nuevos.

## Where we're heading

Business owners should be able to follow each receipt through its whole life in one place, in the currency it was issued in. That life runs from received to reviewed, to paid or collected, to exported. At any moment the owner should know what needs their action.

## Working on Cuadrao

- [Product overview](docs/PRODUCT.md): audience, purpose, and behavior.
- [Documentation authority](docs/DOCUMENTATION_AUTHORITY.md): what each document owns and where historical work belongs.
- [AGENTS.md](AGENTS.md): codebase facts, checks, and safety rules for coding agents.
- The integration branch is `codex/private-alpha-next`. Open pull requests against it.
- Some older Argus code remains in the repository under `src/argus/`.

Technical work starts from an explicit assignment and the relevant architecture, API, and data contracts.
