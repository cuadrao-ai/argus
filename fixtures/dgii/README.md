# Mocks DGII Formato 606 / 607 — PRÁCTICA / DATOS FICTICIOS

Reference target for Cuadrao's export. All identities are fake. They only pass the check digit. **Do not send to DGII.**
Regenerate with `.venv/bin/python generate.py` (needs openpyxl). The script also validates its own output against the rules below.

| File | What it is |
|---|---|
| `606_mock_202609.txt` / `DGII_F_606_139999001_202609.TXT` | 606 TXT, 15 lines (the second name is the one DGII's tool produces) |
| `607_mock_202609.txt` / `DGII_F_607_139999001_202609.TXT` | 607 TXT, 10 lines |
| `606_mock_202609.xlsx`, `607_mock_202609.xlsx` | Copies of the official sheet layout (header block rows 4–7, column numbers row 10, titles row 11, detail from row 12). 607 has a second sheet with the consumer-invoice summary that goes into the OFV |
| `resumen_ITBIS_202609.md` | ITBIS and month result, computed by the script |
| `preview_606.png`, `preview_607.png` | Render of the xlsx |
| `sources/` | Official DGII zips, instructivos (PDF + txt) and the VBA macros extracted with olevba (`vba606.txt`, `vba607c.txt`) |

**Main source of truth:** the `GenerarArchivo` macro inside DGII's official Excel tools (606 "Versión 2025", zip modified 28/10/2025; 607 "Version 2023.1.1"). The layout below comes straight from that code, not from third-party blogs.

## TXT file structure (both formats)
- Header: `606|RNC_o_Cédula|AAAAMM|CantidadRegistros` (607 is the same with `607|`). For periods ≥ 201501 it carries **no** total amount.
- One detail line per NCF, fields separated by `|`, no quotes, no padding (`Trim` on each cell). Empty fields stay empty (`||`).
- Line breaks are CRLF (VBA `Print #` on Windows). **The last line has no line break** (`Print #1, strDetalle;`). The mock follows this exactly.
- Name produced by DGII's tool: `DGII_F_606_<RNC>_<AAAAMM>.TXT`.
- Maximum 10,000 records (606) and 65,000 (607).
- Amounts use a decimal point and no thousands separator (instructivo: "digite el punto decimal… RD$10.18"). The tool writes the cell text as is; the mock always uses 2 decimals.

## 606 — Compras de Bienes y Servicios (23 detail fields)
| # | Excel title (exact) | TXT format | Required? | Notes |
|---|---|---|---|---|
| 1 | RNC o Cédula | 9 digits (RNC) or 11 (cédula) | Yes | Numeric. For B13 (gastos menores) it must equal the header RNC. For B17 (pagos al exterior) the header RNC is used |
| 2 | Tipo Id | `1`=RNC, `2`=Cédula | Yes | The tool infers it from the length (>9 → 2) |
| 3 | Tipo Bienes y Servicios Comprados | `01`–`11` (2 digits) | Yes | 01 Personal, 02 Trabajos/suministros/servicios, 03 Arrendamientos, 04 Activos fijos, 05 Representación, 06 Otras deducciones admitidas, 07 Financieros, 08 Extraordinarios, 09 Costo de venta, 10 Adquisiciones de activos, 11 Seguros |
| 4 | NCF | 11 (B), 13 (e-NCF E), 19 (old pre-2018) | Yes | Tool regex: `B(01-04\|11-15\|17)########` or `E(31-34\|41-45\|47)##########` |
| 5 | NCF ó Documento Modificado | same as 4 | Only for B03/B04 (notes) | NCF affected by the debit/credit note |
| 6 | Fecha Comprobante | `AAAAMMDD` | Yes | Excel splits it into AAAAMM + DD; the TXT joins them (`ConcatFecha_one`) |
| 7 | Fecha Pago | `AAAAMMDD` or empty | Required if there is a retention | Blank if not paid |
| 8 | Monto Facturado en Servicios | decimal ≥ 0 | Optional | Excluding taxes |
| 9 | Monto Facturado en Bienes | decimal ≥ 0 | Optional | Excluding taxes |
| 10 | Total Monto Facturado | decimal > 0 | Yes (calculated) | = 8 + 9 |
| 11 | ITBIS Facturado | decimal | Yes (can be 0) | |
| 12 | ITBIS Retenido | decimal ≥ 0 | Optional | Requires field 7 |
| 13 | ITBIS sujeto a Proporcionalidad (Art. 349) | decimal ≥ 0 | Optional | Feeds Anexo A of the IT-1 |
| 14 | ITBIS llevado al Costo | decimal ≥ 0 | Optional | Not deducted as an advance |
| 15 | ITBIS por Adelantar | decimal | Calculated | = 11 − 14 |
| 16 | ITBIS percibido en compras | decimal | Leave empty | "no estará habilitado" until there is a perception regime |
| 17 | Tipo de Retención en ISR | `01`–`09` | Optional | 01 Alquileres, 02 Honorarios, 03 Otras rentas, 04 Rentas presuntas, 05 Intereses PJ, 06 Intereses PF, 07 Proveedores del Estado, 08 Juegos telefónicos, 09 Ganadería bovina. Requires field 7 |
| 18 | Monto Retención Renta | decimal ≥ 0 | Optional | Requires field 7 |
| 19 | ISR Percibido en compras | decimal | Leave empty | Not enabled |
| 20 | Impuesto Selectivo al Consumo | decimal ≥ 0 | Optional | |
| 21 | Otros Impuesto/Tasas | decimal ≥ 0 | Optional | |
| 22 | Monto Propina Legal | decimal ≥ 0 | Optional | 10%, Ley 54-32 |
| 23 | Forma de Pago | `01`–`07` | Yes | 01 Efectivo, 02 Cheques/Transferencias/Depósito, 03 Tarjeta crédito/débito, 04 Compra a crédito, 05 Permuta, 06 Notas de crédito, 07 Mixto |

## 607 — Ventas de Bienes y Servicios (23 detail fields)
| # | Excel title (exact) | TXT format | Required? | Notes |
|---|---|---|---|---|
| 1 | RNC/Cédula o Pasaporte | 9 / 11 digits / passport | Yes* | *Except notes (B03/B04) that modify a B02 under the threshold. For B12 it must equal the header. Cédula `00000000000` is rejected |
| 2 | Tipo Identificación | `1` RNC, `2` Cédula, `3` Pasaporte/ID tributaria | Yes* | |
| 3 | Número Comprobante Fiscal | 11 or 19 | Yes | Tool regex: `B(01-04\|11-16)########`. **No E series** |
| 4 | Número Comprobante Fiscal Modificado | 11 or 19 | Notes only | |
| 5 | Tipo de Ingreso | **1 digit** `1`–`6` | Yes | The macro takes `Mid(cell,2,1)` of "01 - …". 1 Operaciones (no financieros), 2 Financieros, 3 Extraordinarios, 4 Arrendamientos, 5 Venta de activo depreciable, 6 Otros |
| 6 | Fecha Comprobante | `AAAAMMDD` | Yes | |
| 7 | Fecha de Retención | `AAAAMMDD` or empty | Required if 10 or 12 is filled | |
| 8 | Monto Facturado | decimal | Yes | Excluding taxes |
| 9 | ITBIS Facturado | decimal | Yes (can be 0) | |
| 10 | ITBIS Retenido por Terceros | ≤12 characters, ≥ 0 | Optional | |
| 11 | ITBIS Percibido | | Leave empty | Not enabled |
| 12 | Retención Renta por Terceros | ≤12 characters, ≥ 0 | Optional | |
| 13 | ISR Percibido | | Leave empty | Not enabled |
| 14 | Impuesto Selectivo al Consumo | ≤12 | Optional | |
| 15 | Otros Impuestos/Tasas | ≤12 | Optional | |
| 16 | Monto Propina Legal | ≤12 | Optional | |
| 17 | Efectivo | ≤12 | ≥1 of 17–23 | |
| 18 | Cheque/ Transferencia/ Depósito | ≤12 | ″ | |
| 19 | Tarjeta Débito/Crédito | ≤12 | ″ | |
| 20 | Venta a Crédito | ≤12 | ″ | |
| 21 | Bonos o Certificados de Regalo | ≤12 | ″ | |
| 22 | Permuta | ≤12 | ″ | |
| 23 | Otras Formas de Ventas | ≤12 | ″ | Sum of 17–23 = invoice total **with taxes**. Credit notes (B04) are exempt |

**Facturas de consumo (B02):** those **under RD$250,000** do NOT go in the TXT. They are reported as a total in the OFV under "Resumen General de Facturas de Consumo": number of NCFs, monto, ITBIS, ISC, otros, propina, tipo de venta. That summary covers ALL B02 invoices, including those ≥ 250k, which also go line by line in the TXT with the buyer's ID. The tool has the threshold set at 250,000 from 201807 (it was 50,000 under the original NG 07-2018).

## Rejection rules (tool / Pre-validación / OFV)
1. RNC is 9 digits and cédula is 11, numeric. The type must match the length.
2. NCF matches the regex and has the right length (11/13/19). The B or E series must be valid for the format.
3. Dates are valid calendar `AAAAMMDD` (regex rejects 31/04, 30/02, etc.). Period is `AAAAMM` and ≥ 201805.
4. Header record count = number of lines. Field count = 23 per line.
5. Amounts are numeric and ≥ 0. Total monto facturado is > 0 (606).
6. Any retention (ITBIS/ISR) requires Fecha Pago (606) / Fecha de Retención (607).
7. B13 (606) and B12 (607) use the header RNC.
8. 607: at least one payment method has a value (except B04), and the sum equals the invoice total.
9. B04 subtracts from the totals. A credit note whose affected NCF was never reported triggers an alert.
10. After submission (OFV, ~30 min) the alerts are: RNC inactivo, NCF no habilitado, NCF no existe/eliminado, NCF no autorizado, **NCF ya reportado (duplicate)**, NC sin NCF afectado, B11 issued to a cédula that is registered as a taxpayer, crédito fiscal from an unregistered RNC, and an e-CF whose issuer/receiver doesn't match or that isn't registered as an electronic issuer. **The mock will always fail these** because its RNCs/NCFs don't exist at DGII.
11. Check digit: the official algorithm is in `modUtilities.GenDV_Para_Republica_Dominicana`. RNC weights 7-9-8-6-5-4-3-2 mod 11 (r=0→2, r=1→1, else 11−r). Cédula uses Luhn with weights 1-2-1-2…. **Note:** in both tools the DV check is commented out, so DGII validates this server-side, not in Excel. The mock passes it anyway.

## Uncertain / unverified (do not assume)
- **e-CF:** the 606 instructivo (July 2025) says e-CF received from electronic issuers must be included in the 606, and the tool accepts the E series. Some answers in the DGII community say the opposite: an electronic issuer should not report e-CF in the 606. The mock includes one E31 line. **A contador should confirm.** The 607 tool doesn't accept the E series. According to the DGII community, an issuer with 100% e-CF does not send the 607/608.
- Retention rates in the mock (ITBIS 100% + ISR 10% for a persona física professional, ITBIS 30% retained by a corporate client, ISR 5% for proveedor del Estado) are **illustrative**. I didn't check them against the Norma 02-05/07-07 text.
- Tax treatment in the mock: insurance with ISC 16% and no ITBIS, telecom ISC 10% + CDT 2% under "Otros", bank commissions exempt. These are common practice; I didn't check them against an official source.
- Amount format: the official tool writes the cell text as is (could be `3000` or `3000.5`). I'm assuming DGII accepts 2 fixed decimals; I didn't check the Pre-validador.
- File encoding: everything is ASCII here, so this doesn't come up. I didn't check what encoding DGII expects if names/accents appear (they don't appear in the TXT).
- The ITBIS summary is a product approximation (no proporcionalidad, saldos a favor, IT-1 anexos, or IR-17). It is not the IT-1.
- Labels "(ITBIS Fact.)/(ITBIS Ret.)/(Ret. Renta)" in row 6 of the 606 xlsx are my own. In the official tool those cells have no visible text label.
- The fake RNCs/cédulas pass the DV, so they could match a real taxpayer. They aren't checked against DGII's registry. Use them only in testing.

## Sources (all downloaded 2026-10-18)
- Formatos de Envío de Datos page: https://dgii.gov.do/herramientas/formularios/formatoEnvioDatos/Paginas/default.aspx (`sources/formatoEnvioDatos_page.html`)
- 606 tool + instructivo (zip 28/10/2025): https://dgii.gov.do/herramientas/formularios/formatoEnvioDatos/Documents/Formato%20de%20compras,%20bienes%20y%20servicios/Formato-de-Envio-606-(NG-07-2018-y-05-2019).zip
- 607 tool + instructivo: https://dgii.gov.do/herramientas/formularios/formatoEnvioDatos/Documents/Formato%20de%20ventas%20bienes%20y%20servicios/Formato-de-Envio-607-(NG-07-2018-y-05-2019).zip
- Instructivo 606 (web copy): https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/formatoEnvioDatos/Documents/4-LlenadoyEnvioFormato606.pdf
- Instructivo 607: https://dgii.gov.do/publicacionesOficiales/bibliotecaVirtual/contribuyentes/formatoEnvioDatos/Documents/5-InstructivoLlenadoyenvioFomato607.pdf
- Norma General 07-2018: https://dgii.gov.do/legislacion/normasGenerales/Documents/NG%20sobre%20Comprobantes%20Fiscales/Norma07-18.pdf (not downloaded, read via search)
- DGII community (consumo < 250k): https://ayuda.dgii.gov.do/conversations/discusiones/ingresos-607/6585b7e8c99bc66ce07c0d01
- DGII community (e-CF and 607/608): https://ayuda.dgii.gov.do/conversations/discusiones/envo-607-con-facturacin-electrnica/68430e986b60527a3ecceb48 , https://ayuda.dgii.gov.do/conversations/discusiones/eliminacion-envio-606607/650eeb9fcc94fb3f6633066c
- DGII community (structure unchanged): https://ayuda.dgii.gov.do/conversations/discusiones/nuevo-formato-del-606-existe-documentacin-o-guas-para-su-uso/686d50710b8266586ce5d6a1
