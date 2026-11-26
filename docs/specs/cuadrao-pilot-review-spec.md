# Cuadrao pilot review spec

**Status:** approved plan, October 31, 2026. A receipt with no NCF needs attention (founder decision).
**Scope:** Bandeja, the receipt dossier and month close for the José pilot.
**Out of scope:** archive (#1638), the invoice cascade (#1639), USD rate handling, and email and WhatsApp changes.

## One rule

A receipt lives in one place. It is in Bandeja until it is approved. After that it is in Registros. Inicio links a waiting row back to its record.

| Stage | Where |
| --- | --- |
| Received, reading, needs attention, ready | Bandeja |
| Approved | Registros |

## Bandeja

The [Bandeja design](../../.agent/designs/cuadrao-business-app/DESIGN.md#bandeja) owns the tabs, columns, filters and row actions.

### Listos

See [Bandeja tabs](../../.agent/designs/cuadrao-business-app/DESIGN.md#tabs), [labels](../../.agent/designs/cuadrao-business-app/DESIGN.md#labels) and [row actions](../../.agent/designs/cuadrao-business-app/DESIGN.md#rows).

## Dossier

See [Receipt detail](../../.agent/designs/cuadrao-business-app/DESIGN.md#receipt-detail) for the layout, the fields a person can edit and how a record is reviewed.

## Approval and the 606

Approval confirms that the read is right and that the record counts. It needs no 606 data, no account and no payment answer. Parte del negocio does not block. The server accepts 606 data after approval, and an export freezes nothing: 606 data, the Personal mark and the 606 answer stay editable, and the next export carries the change. The founder accepts that the app and a filed TXT can differ (2026-11-02). The RNC status and list date are saved on the record at approval.

Payment is a separate, optional step. An approved purchase or sale is pendiente until a person marks it paid or collected, with a method. No account is needed. Forma de pago stays blank until a person or the receipt sets it, and month close lists it as missing. Cuadrao never fills it with a default.

## Month close

It lives in Registros, as a monthly step. It lists what is missing for the 606, and the owner can fill many rows at once. Inicio shows one reminder that opens this view. A foreign-currency line keeps today's behavior until José tells us how he declares it.

## DGII list

One current row per RNC or cédula, replaced by the daily load, with no history table. Load every row, not only active ones, so a suspended or cancelled supplier is flagged. The CSV is the source. Keep razón social, actividad económica, fecha de inicio, estado and régimen. The file has no trade name and no e-invoice field. There is no per-record lookup in the pilot.

The review shows the DGII legal name and status in place of "RNC sin verificar", and raises Suspendido and Dado de baja. Business setup takes an RNC or cédula, fills the legal name, status and activity, and the person confirms and types the trade name.

## Typed entry

Creating a typed entry is off for the pilot. `CUADRAO_BUSINESS_TYPED_NOTES_ENABLED` turns it on and is off by default. Entries saved before still show in Bandeja.

Agregar has a small typed entry for a purchase with no paper: amount, date, and supplier or description. It is saved as sin comprobante, counts in the books, stays out of the 606, and a person reviews it. The Registros note editor stays off.

## Pilot setup

José is an accountant who runs client Businesses. For the one pilot client, José holds the Dueño seat and approves. This is a setup choice, not a rule about who owns a business. The client agrees, need not log in, and can be invited as Lector. There are no role or permission changes.

## States

- **Empty:** reuse the existing art, with text for an empty Listos and an empty Por resolver.
- **Loading:** the skeleton follows the final columns and the Listos checkboxes.
- **Offline:** the existing connection banner shows in the Business app.
- **Failure:** every failure shows what was refused, a `Ref.`, and a way out.

### Session and identity recovery

Mounted workspace session checks distinguish pending, failed, missing, the same account, and a
confirmed different account. A failed check, including on tab wake or focus,
offers a real retry. A successful check with no session offers login without
claiming expiry or an account change. Only a confirmed different user gets the
account-change notice, followed by clean Home entry after identity and access
verification. Recovery never replays a save, upload, or approval.

Recovery removes private workspace content and uses a public title. It does not
invent a server reference when none exists. The existing delayed startup loader,
same-account background checks, and intentional logout keep their behavior.
The [Business design guide](../../.agent/designs/cuadrao-business-app/DESIGN.md#session-recovery-approved-november-7-2026)
owns the approved layout and interaction rules. The cause of session loss and
session renewal remain outside #1853. The separate server check on a direct
Business page visit still redirects returned errors to login; #1862 tracks that
pre-existing entry behavior.

## Search

Search is the default. The search flag goes away.

## Done means

Upload, review, approve, and month close work end to end on staging, with synthetic receipts and at the recorded SHA.
