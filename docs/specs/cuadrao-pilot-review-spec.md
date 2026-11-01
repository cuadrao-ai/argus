# Cuadrao pilot review spec

**Status:** approved plan, October 31, 2026. A receipt with no NCF needs attention (founder decision).
**Scope:** Bandeja, the receipt dossier and month close for the José pilot.
**Out of scope:** archive (#1638), the invoice cascade (#1639), USD rate handling, and email and WhatsApp changes.

## One rule

A receipt lives in one place. It is in Bandeja until it is approved. After that it is in Registros. Inicio only counts.

| Stage | Where |
| --- | --- |
| Received, reading, needs attention, ready | Bandeja |
| Approved | Registros |

## Bandeja

Tabs: **Todos · Necesitan atención · Listos**. Bandeja opens on Todos. Todos has no count. The other tabs show one server count, and the sidebar and Inicio use the same count.

Columns: Contenido, Adjunto, Canal, Remitente, Estado, Llegada, action. Monto and Moneda stay off by default. The row stays a table on normal laptops. Cards are for phone size only.

Row tags: Leyendo, Necesita atención with its reason, Listo para aprobar, Aprobado.

Removed from live: En proceso, Más acciones.

### Listos

A receipt is Listos only when the server confirms all of these:

- The read finished, and nothing is missing from the six facts.
- It has a valid NCF or e-CF.
- It has an RNC with a valid check digit.
- Its currency is DOP.
- It has no duplicate and no review flag.
- Its sender is verified, if it came by email.

Every other open receipt is in Necesitan atención, with one plain reason.

**Aprobar todos:** the owner selects rows or takes all of them, sees the count, and confirms. Only the owner sees this action. Nothing is approved without the owner. If some fail, the screen says which, and those stay in Listos. Selection does not change when a new receipt arrives.

## Dossier

The base is the staging dossier: the original on one side, and Historial stays.

**Step 1, six read facts:** supplier, date, total with currency, RNC, NCF or e-CF, ITBIS. Every fact is editable in place.

**Step 2, two owner choices:** tipo de gasto (José's 11) and forma de pago (José's 7). Both are offered and neither blocks approval. Forma de pago is filled when the receipt prints it. Tipo de gasto is filled from the last choice for that RNC. The owner can change both.

**Step 3, hidden:** other 606 fields sit closed under "Más datos fiscales".

The top box lists only what blocks approval. An edit shows a saved state. Leaving with unsaved edits warns first. Clicking outside closes the dossier, with the same warning. Every refusal shows a clear message and a `Ref.`.

Removed: Confirmar datos leídos, the Comprobante row, Consultar registro actual, and the old Categoría list. Personal stays for the design pass.

## Approval and the 606

Approval confirms that the read is right. It does not need 606 data. The server accepts 606 data after approval, until the record is exported. The RNC status and list date are saved on the record at approval.

## Month close

It lives in Registros, as a monthly step. It lists what is missing for the 606, and the owner can fill many rows at once. Inicio shows one reminder that opens this view. A foreign-currency line keeps today's behavior until José tells us how he declares it.

## DGII list

One current row per RNC, replaced by the daily load. There is no history table. Keep the useful fields the download holds: name, trade name, status, and activity and e-invoice status if the file has them. The review shows the DGII name and status in place of "RNC sin verificar".

## States

- **Empty:** reuse the existing art, with text for an empty Listos and an empty Necesitan atención.
- **Loading:** the skeleton follows the final columns and the Listos checkboxes.
- **Offline:** the existing connection banner shows in the Business app.
- **Failure:** every failure shows what was refused, a `Ref.`, and a way out.

## Search

Search is the default. The search flag goes away.

## Done means

Upload, review, approve, and month close work end to end on staging, with synthetic receipts and at the recorded SHA.
