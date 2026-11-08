# Cuadrao pilot field dictionary

Source of truth for Business pilot labels and semantics across the dossier, Más datos, Registros, export headers, and DGII columns. Storage keys are unchanged.

The label map is locked for the Dominican Republic Business pilot as of November 5, 2026, CT. This document records product intent. It does not claim every label is implemented.

## Locale and editing rules

- ES UI uses Spanish labels and Spanish option text.
- EN UI uses English labels and English option text. Spanish option strings do not appear in English UI.
- Tipo de gasto codes 01–11 and Forma de pago codes 01–07 are fixed across locales.
- The 12-column pilot export keeps its exact Spanish headers as that file format, even in EN UI.
- `category` and `payment_method` are edited on "Para el 606", not inside the Más datos editor. Their rows below describe shared field semantics, not extra editor controls.
- Tipo Id displays `1 - RNC` / `2 - Cédula`.

The tables preserve the confirmed engineering map's keys. Registros column keys and derived values are identified separately from stored fields.

## Core facts by surface

| Canonical key | Dossier main (ES / EN) | Más datos fiscales (ES / EN) | Registros column (ES / EN) | Pilot 12-column export (exact) | DGII 606/23 (exact) | Notes |
|---|---|---|---|---|---|---|
| counterparty | Contraparte / Counterparty | — | Contraparte / Counterparty | — | — | Name only. Never show RNC here. Use Contraparte on both dossier and Registros. Optional helper: "comercio o persona del comprobante". "Comercio o persona" is not the label. |
| rnc | RNC / RNC | — | — (not a column) | RNC EMISOR | RNC o Cédula | Identity number. Distinct from Contraparte. |
| id_type | — | Tipo Id / ID type | — | — (the pilot sheet has none) | Tipo Id | Values: `1` = RNC, `2` = Cédula. Show as "1 - RNC" / "2 - Cédula". |
| occurred_on | Fecha del comprobante / Receipt date | — | Fecha / Date | FECHA DEL COMPROBANTE | Fecha Comprobante | One meaning; column shortens the same phrase. "Fecha de actividad" is not the label. |
| amount | Monto / Amount | — | Monto {{currency}} / Amount {{currency}} | TOTAL | — | **Gross** (what the receipt shows). The pilot TOTAL export rule: use `amount` when present; else servicios+bienes+itbis. Not DGII net. |
| (derived) total_monto_facturado | — | — | — | — | Total Monto Facturado | **Net** = servicios + bienes. Never label this "Monto" or "TOTAL". |
| currency | Moneda / Currency | — | Moneda / Currency | — | — | |
| ncf / ecf | NCF / e-CF / NCF / e-CF | — | — | NCF | NCF | |
| modified_ncf | — | NCF ó Documento Modificado / Modified NCF or document | — | NCF AFECTADO | NCF ó Documento Modificado | |
| itbis | ITBIS / ITBIS | — | — | ITBIS FACTURADO | ITBIS Facturado | |
| document_type | Tipo (Compra / Venta) / Type (Purchase / Sale) | — | Tipo / Type | — | — | Registros `detalle` today. Keep Compra/Venta. |
| category | Tipo de gasto / Expense type | — | Tipo de gasto / Expense type | TIPO DE BIENES Y/O SERVICIOS COMPRADOS | Tipo Bienes y Servicios | Field title in app stays "Tipo de gasto"; export header is the pilot's exact phrase. Option **codes** 01–11 fixed; option **text** follows UI locale. |
| payment_method | Forma de pago / Payment method | — | Forma de pago / Payment method | FORMA DE PAGO | Forma de Pago | Option codes 01–07 fixed; option text follows UI locale. Distinct from Cuenta. |
| services_amount | — | Monto Facturado en Servicios / Amount billed for services | — | MONTO FACTURADO EN SERVICIOS | Monto Facturado en Servicios | Reader split waits; field stays for export and edit. |
| goods_amount | — | Monto Facturado en Bienes / Amount billed for goods | — | MONTO FACTURADO EN BIENES | Monto Facturado en Bienes | Reader split waits; field stays for export and edit. |
| selective_tax | — | Impuesto Selectivo al Consumo / Excise tax | — | IMPUESTO SELECTIVO AL CONSUMO | Impuesto Selectivo al Consumo | |
| legal_tip | — | Monto Propina Legal / Legal tip amount | — | MONTO DE PROPINA LEGAL | Monto Propina Legal | |
| paid_on | — | Fecha Pago / Payment date | — | — | Fecha Pago | 606 only; not on the pilot 12. |
| other_taxes | — | Otros Impuesto/Tasas / Other taxes/fees | — | — | Otros Impuesto/Tasas | 606 wording. 607 uses "Otros Impuestos/Tasas". |

### Option lists (codes locked; text follows UI locale)

**Codes (never change):**
Tipo de gasto: 01–11 · Forma de pago: 01–07

**ES UI / the pilot export / DGII** (official Spanish):
01 Gastos de personal · 02 Gastos por trabajos, suministros y servicios · 03 Arrendamientos · 04 Gastos de activos fijo · 05 Gastos de representación · 06 Otras deducciones admitidas · 07 Gastos financieros · 08 Gastos extraordinarios · 09 Compras y gastos que formarán parte del costo de venta · 10 Adquisiciones de activos · 11 Gastos de seguros

01 Efectivo · 02 Cheques/transferencias/depósito · 03 Tarjeta crédito/débito · 04 Compra a crédito · 05 Permuta · 06 Nota de crédito · 07 Mixto

**EN UI:** translate the option text; keep the same codes. Do not show Spanish option strings inside an English UI.

---

## Conditional and secondary dossier fields

| Key | ES | EN | Pilot note |
|---|---|---|---|
| kind | Actividad | Activity | |
| funding | Compra: Cómo se pagó; Venta: Forma de cobro | Purchase: How it was paid; Sale: Collection method | App funding story; distinct from the 607 Forma de pago fiscal. |
| business_share | Parte del negocio | Business share | |
| partial amount | Monto del negocio | Business amount | |
| receipt_state | Marcar sin recibo | Mark as no receipt | |
| personal | Personal | Personal | |
| include_606 | ¿Incluir en 606? | Include in 606? | |
| dgii.form | Formato | Format | |

---

## Más datos for 606

| Key | ES | EN |
|---|---|---|
| itbis_withheld | ITBIS Retenido | ITBIS withheld |
| itbis_proportionality | ITBIS sujeto a Proporcionalidad (Art. 349) | ITBIS subject to proportionality (Art. 349) |
| itbis_cost | ITBIS llevado al Costo | ITBIS taken to cost |
| itbis_perceived | ITBIS percibido en compras | ITBIS perceived on purchases |
| income_withholding_type | Tipo de Retención en ISR | Income withholding type |
| income_withheld | Monto Retención Renta | Income tax withheld |
| income_perceived | ISR Percibido en compras | Income tax perceived on purchases |
| actual_refund | Se recibió un reembolso… | A refund was received… |
| purchase_activity_id | Compra original | Original purchase |

## Más datos for 607

| Key | ES | EN |
|---|---|---|
| id_type | Tipo Identificación | Identification type |
| modified_ncf | Número Comprobante Fiscal Modificado | Modified fiscal receipt number |
| income_type | Tipo de Ingreso | Income type |
| withheld_on | Fecha de Retención | Withholding date |
| billed_amount | Monto Facturado | Amount billed |
| cash / bank / card / credit / gift / barter / other_payment | Efectivo / Cheque·Transferencia·Depósito / Tarjeta / Venta a Crédito / Bonos… / Permuta / Otras Formas… | Cash / Check·transfer·deposit / Card / Sale on credit / Vouchers… / Barter / Other… |
| itbis_perceived | ITBIS Percibido | ITBIS perceived |
| itbis_withheld_by_third_parties | ITBIS Retenido por Terceros | ITBIS withheld by third parties |
| income_withheld_by_third_parties | Retención Renta por Terceros | Income tax withheld by third parties |
| income_perceived | ISR Percibido | Income tax perceived |

---

## Registros columns

The backend `Presentation` in `src/argus/domain/business/reporting_preferences.py` owns the default layout. The report answer returns the effective `presentation`; the connected table uses it. The preview uses `web/test-fixtures/records-default-report-answer.json`, recorded from the backend. `test_recorded_preview_answer_matches_backend` checks that fixture and `records-default-authority.test.ts` prevents web defaults. Saved layouts keep their explicit order, hidden columns and density. The existing column picker stays. Further table additions wait for the pilot client’s workflow.

| Column key | Pilot default | ES / EN | Why |
|---|---|---|---|
| contraparte | On | Contraparte / Counterparty | |
| fecha | On | Fecha / Date | Short for Fecha del comprobante |
| monto | On | Monto / Amount | Gross |
| moneda | On | Moneda / Currency | |
| detalle | On | Tipo / Type | Compra/Venta |
| tipo_gasto | Available (hidden by default) | Tipo de gasto / Expense type | Applies to purchases only, so hidden by default |
| forma_pago | Available (hidden by default) | Forma de pago / Payment method | Applies to purchases only, so hidden by default |
| estado | On | Estado / Status | |
| comprobante | On | Adjunto / Attachment | |
| notas | On | Notas / Notes | Notas stays available, not stripped or forced hidden. |
| cuenta | Available (hidden by default) | Cuenta / Account | Forma de pago ≠ Cuenta |
| ncf | Available (hidden by default) | NCF / NCF | Existing `fiscal_number`, NCF or e-CF; missing stays unknown |
| itbis | Available (hidden by default) | ITBIS / ITBIS | Existing `itbis_amount` in the row currency; missing amount or currency stays unknown, zero stays numeric |

NCF afectado, servicios, bienes, ISC, and propina legal are pilot export fields, not Registros columns today. Further table additions wait for the pilot client’s workflow. These are semantic targets, not a ship list. They already exist in Más datos or export. The evolved export column and file-type picker is out of scope.

## Score cards

Home card renames are deferred. Keep Ingresos / Gastos. No Home Ingresos-to-Ventas rename is included.

Registros has six summary cards. Lucas approved the purchase-side meanings on 2026-11-07, following the 2026-11-06 review with Iris. Exactly one record type is selected, Compras by default or Ventas. The table and all six cards follow that selection. Ventas uses the existing server values; its cards have not had their design round yet. Missing sales Bienes or Servicios stay unknown.

| Card | Meaning |
|---|---|
| Total | Selected record type gross amount from the server, using the existing source and fallback rules. Static, like ITBIS, with no click, directional cue, hover action or subcard. |
| ITBIS | Selected record type tax amount only. Static. |
| Cantidad | The server's `matching_count` for the current table filters, as a whole number. Static. |
| Bienes | Populated net (pre-tax) goods amounts, including values entered by hand. Its own coverage helper reports populated purchases, for example "12 de 25 compras". Static. |
| Servicios | Populated net (pre-tax) services amounts, including values entered by hand. Its own coverage helper reports populated purchases, for example "12 de 25 compras". Static. |
| Faltan datos fiscales | Server count by the existing fiscal-completeness definition within all current table filters, across all pages. It is the only action card. Its action narrows the status selection to missing fiscal data. A second click restores the previous status selection and preserves the other current filters. The active filter stays visible and clearable. |

Missing Bienes or Servicios values are not zero. Total is not forced to equal Bienes + Servicios + ITBIS. Registros always selects exactly one currency, DOP, USD or EUR. Without a valid single-currency URL or view, the server workspace `records_default_currency` supplies the selection, currently DOP. Never add incompatible currencies. A fiscal amount that its currency cannot represent exactly is not summed, is counted and shown as unsupported, and is never rounded.

The same single-type, single-currency request scopes the table, all six cards and the Registros export. Compras / Ventas are always-visible tabs above the cards, Compras by default, using Bandeja’s tab component. Optional filters are shared across tabs. Moneda is an always-visible DOP / USD / EUR selector beside the period, without search. Neither belongs in Filtros or its chips. The filter count and dots include only optional filters. Clear filters clears only optional filters, keeps the tab, currency, period and search, and is disabled in the editor when none are active. Switching currency clears both amount limits without conversion. Cards describe all matching records across all pages; changing pages does not change their totals. A new request hides the previous card values until its answer arrives. An empty answer shows zero matching records and no invented money amounts.

Known limitations:

- Bienes and Servicios coverage counts applicable purchases only.

Listos para exportar and Ya exportados stay out of the summary. Export workflows and data are untouched.

The server supplies every number; the web computes none. [#1842](https://github.com/cuadrao-ai/argus/issues/1842) adds server totals for ITBIS, Bienes and Servicios, with coverage for Bienes and Servicios.

Registros has no Total or payment subcards. Pagado, Por pagar, Cobrado, and Por cobrar never show. Their data and calculation paths stay. Forma de pago and other fiscal fields are untouched.

Do **not** label a non-fiscal expense total as "Compras (606)".

---

## Semantic traps

- RNC ≠ Contraparte. RNC is the identity number. Contraparte is the name.
- Monto/gross TOTAL ≠ DGII Total Monto Facturado (net). DGII net is servicios + bienes.
- Forma de pago ≠ Cuenta.
- TOTAL export rule: use `amount` when present; else servicios+bienes+itbis.

## Out of scope

- The evolved export column and file-type picker.
- Home card renames, including Ingresos to Ventas.
- App, code, and i18n changes. Their ship order stays parked until an explicit implementation request.
- Storage key changes.
