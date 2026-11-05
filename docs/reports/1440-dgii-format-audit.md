# Issue 1440 part 1: 606 format comparison

## Result and boundary

The existing 23-field 606 serialization matches the provided workbook's TXT generator for the supported purchase fields. The PR adds regression tests and this audit. No production serializer change was justified by the comparison. This is a read-only inspection of the workbook's cells, BIFF validation records and VBA source, plus synthetic serialization checks. The native workbook macros were not executed and no filing was submitted. The export's `official_validation: NOT RUN` and `official_tool_verified: false` remain correct.

The supplied workbook is `Formato-de-Envio-606-(NG-07-2018-y-05-2019)-1.xls`, version 2020.2. Its SHA-256 is `758e2204bedd3ff8d6a9ffa2914898c95e36527eadd1734a97727fc71fd1f650`. The attached copy has the requested filename and 1,711,104-byte size. The inaccessible Downloads original could not be hashed, so byte identity with that original was not independently proven. No other external source was used.

The audit was refreshed after #1788 merged, against fetched integration SHA
`39274cae36252af3f7388bda42c196592916f697`. Only this document and
`tests/dgii/test_official_606_format.py` are changed. The XLS is neither committed
nor required to run the tests. The protected direction and validation files remain
unchanged. This slice does not export real September records.

The required pre-push integration refresh advanced the base to
`66eea7743973aa5c97230c6184eb0b4f55d5c583`; that change concerns a web review count.

## What the tool actually contains

- `UtilitarioP!A1:A168` contains period choices, initially 2007 through 2020. `Module2.ValidationListasGenerar` regenerates these through the current year. It is not the TXT layout.
- `Herramienta Formato 606!B11:Z11` contains the 23 numbered fields. Two date fields each occupy two worksheet columns, so the input area has 25 physical columns.
- `modServicios.GenerarArchivo` owns the TXT header, order, separators and final-line behavior.
- `modServicios.validarDetalle` passes each cell to `clsFormato606Validator` and calculates total billed and ITBIS advance.
- `modConstantesGlobales` identifies all cell positions and the date/NCF patterns. `modUtilities.ConcatFecha_one` joins year/month with a two-digit day.
- Stored data-validation records point to `AD2:AD12` for expense types, `AF2:AF8` for payment methods and `AE4:AE11` for ISR types.

The bundled help text includes older column references and an older tax percentage. The active generator and validation code, rather than those stale help passages, support the following conclusions.

## Column-by-column comparison

Here, "optional" describes the active workbook validator. Our application can impose stricter business eligibility. Amount cells display `#,##0.00`, but the generator reads cell values through `Trim`, not their formatted display. It does not require exactly two decimal places. Our fixed two-decimal ASCII representation with a decimal point is compatible with its numeric checks and `Val` calculations. No grouping separators, currency signs or labels enter the TXT amounts.

| # | Field | Tool input | Required / format in active tool | Our output and conclusion |
|---|---|---|---|---|
| 1 | RNC o Cédula | B | Required numeric text; length 9 for RNC, 11 for cédula | Normalized digits; preserves text identifiers. Match. Our check-digit/registry checks are stricter. |
| 2 | Tipo Id | C | Required `1` or `2`; validator derives it from identifier length | Single digit `1`/`2`; no label or zero padding. Match. |
| 3 | Tipo Bienes y Servicios Comprados | D | Required; dropdown AD2:AD12; generator takes first two characters | `01` through `11`. Match. |
| 4 | NCF | E | Required; validator recognizes B, E and legacy 19-character series | Normalized uppercase B/E identifier. Match for our supported series; legacy forms are intentionally narrower in our app. |
| 5 | NCF ó Documento Modificado | F | Optional; same format checks when supplied | Blank or identifier; our note-reference requirements are stricter. Match. |
| 6 | Fecha Comprobante | G:H | Required; year/month plus day becomes `YYYYMMDD` | `YYYYMMDD`, including zero-padded day. Match within workbook year range 1950..2099. See limits below. |
| 7 | Fecha Pago | I:J | Optional; same eight-character date if supplied | Blank or `YYYYMMDD`. Match. Our retention rules require a payment date in more cases. |
| 8 | Monto Facturado en Servicios | K | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 9 | Monto Facturado en Bienes | L | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 10 | Total Monto Facturado | M | Calculated K+L; required and greater than zero | Services+goods, two decimals; app rejects nonpositive base. Match. This excludes ITBIS and the separately stated taxes/tip. |
| 11 | ITBIS Facturado | N | Dedicated numeric validation is commented out; used in calculations | Required in our app; two decimals, including `0.00`. Compatible, stricter than this validator. |
| 12 | ITBIS Retenido | O | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 13 | ITBIS sujeto a Proporcionalidad | P | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 14 | ITBIS llevado al Costo | Q | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 15 | ITBIS por Adelantar | R | Calculated N-Q; dedicated validation commented out | ITBIS minus cost, two decimals, including `0.00`. Match; app also prevents cost exceeding ITBIS. |
| 16 | ITBIS percibido en compras | S | Optional nonnegative numeric | Always blank; nonzero inputs are refused upstream as unsupported regime. Compatible subset, not complete tool capability. |
| 17 | Tipo de Retención en ISR | T | Optional; generator takes first two characters; selectable list `01`..`08` | Blank or two-digit code. Formatting matches, but our type also permits `09`, absent from this tool's list. Unfixed gap. |
| 18 | Monto Retención Renta | U | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 19 | ISR Percibido en compras | V | Optional nonnegative numeric | Always blank; nonzero inputs are refused upstream. Compatible subset, not complete tool capability. |
| 20 | Impuesto Selectivo al Consumo | W | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 21 | Otros Impuesto/Tasas | X | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 22 | Monto Propina Legal | Y | Optional nonnegative numeric | Blank for absent/zero; otherwise two decimals. Match. |
| 23 | Forma de Pago | Z | Required; dropdown AF2:AF8; first two characters emitted | `01` through `07`. Match. |

## Header and physical TXT format

For the supported modern periods the tool writes `606|<reporter RNC>|<YYYYMM>|<record count>`. There is no total-amount header field. The five-field header branch is for periods before 201501, which this version's header validator already refuses because it requires at least 201805.

Our `_txt` uses the same four fields, pipe delimiters, CRLF between lines, 23 detail fields, no trailing pipe and no newline after the last detail. The tool's final `Print #1, strDetalle;` suppresses that final newline. The tool's text writer has no explicit Unicode encoding. Our emitted digits, uppercase identifiers, punctuation and separators are ASCII, so there is no encoding difference for supported rows. Neither output has a BOM. No column-heading row belongs in the TXT.

## Expense and payment lists

The code sets, order and code-to-meaning mapping match exactly. Labels do not match byte-for-byte: the tool includes code prefixes, uppercase letters, irregular/trailing spaces and a nonbreaking space in the Permuta entry. Our display labels use sentence case and add accents in `formarán` and `crédito`. These are display differences, not TXT code differences.

| Code | Expense meaning, AD2:AD12 |
|---|---|
| 01 | Gastos de personal |
| 02 | Gastos por trabajos, suministros y servicios |
| 03 | Arrendamientos |
| 04 | Gastos de activos fijo |
| 05 | Gastos de representación |
| 06 | Otras deducciones admitidas |
| 07 | Gastos financieros |
| 08 | Gastos extraordinarios |
| 09 | Compras y gastos que formarán parte del costo de venta |
| 10 | Adquisiciones de activos |
| 11 | Gastos de seguros |

| Code | Payment meaning, AF2:AF8 |
|---|---|
| 01 | Efectivo |
| 02 | Cheques/transferencias/depósito |
| 03 | Tarjeta crédito/débito |
| 04 | Compra a crédito |
| 05 | Permuta |
| 06 | Nota de crédito |
| 07 | Mixto |

The worksheet dropdowns contain full prefixed labels, not bare codes. The macro list validator is weaker: it only checks that the first two characters are numeric. Therefore a macro-only numeric-prefix pass does not prove a value belongs to the official dropdown list. We did not treat its permissiveness as permission to add codes.

## Official worksheet handoff

Our `606` review sheet uses the 23-field TXT order and stores its values as text.
The official grid uses 25 cells because each date is split into year/month and
day. Whole-row paste into the official grid is not supported as-is. Dates must
be split, columns repositioned and dropdown-label compatibility handled. The
header and row count must be set through the tool's normal flow; its validator
recalculates M and R. Native paste and dropdown behavior were not executed.
The inspected workbook generates TXT; no TXT-to-grid importer was identified.

## Gaps left unchanged

1. **ISR list.** `contracts/dgii.py` permits `09`; the active worksheet dropdown
   `AE4:AE11` contains only `01` through `08`. `AE3` contains `00 - ` but is outside
   the dropdown range. The macro's numeric-prefix check is more permissive than
   the list and would not itself reject `09`. The declaration owner and its tests
   need a separately authorized change; do not duplicate that list in a formatter.
2. **Tool limits.** Header validation permits 1 through 10,000 records and periods
   `201805` through `209912`. The date regex uses years 1950 through 2099. The
   packet does not enforce all these tool limits; its date types have a wider
   domain. Exact parity needs a coordinated change to packet/header validation
   and the protected validation owner. No out-of-range filing was attempted.
3. **Worksheet handoff.** The review sheet is a TXT review surface, not a direct
   paste template for the official grid. Changing it requires an explicit scope
   for the workbook owner in `dgii_export.py`. Its current representation is
   documented and tested without treating it as native paste compatibility.
4. **Supported regimes.** Nonzero ITBIS/ISR perceptions are deliberately refused
   upstream, rather than silently discarded from an emitted TXT. Legacy NCFs,
   some series choices and application eligibility rules are narrower than the
   workbook validator. This audit does not expand fiscal product support.
5. **Native acceptance.** No native macros or official filing service were run.
   Source compatibility and synthetic tests are not an official validation
   receipt. Both existing verification flags remain unchanged.

## Regression evidence

`tests/dgii/test_official_606_format.py` uses deterministic synthetic records.
Identity values have the appropriate length and check digit. Every code-pair case
passes the public packet builder's eligibility checks before comparing all 23
serialized positions with an independent, workbook-derived expected order.

Coverage includes all 154 combinations of 11 expense codes, seven payment codes
and two identity types, optional blank/zero handling, required-code refusals,
unsupported-perception refusals, exact TXT header/framing, the review workbook's
text values and both dropdown code-to-label mappings. Display-label comparisons
normalize case and accents; the report above explicitly records that the labels
are not byte-for-byte identical. No code list is derived from the production
table to decide which combinations to test.

These are assurance tests for existing behavior, not a claimed runtime fix.
The source workbook is inspected read-only; tests do not execute its VBA or open
it in CI. Verification results and any environment blockers are in the PR body.
