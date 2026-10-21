/** One pending invoice: a month with no documents shows its empty state instead of the figure cards. */
const PENDING_INVOICE = {
  activity_id: "wire-invoice-1",
  document_kind: "invoice",
  occurred_on: "2026-10-05",
  total_minor: 5_900_000,
  itbis_minor: 900_000,
  status: "pendiente",
  currency: "DOP",
  counterparty: "Colmado La Esquina",
};

export function monthCloseWire(month: string) {
  const [year, index] = month.split("-").map(Number);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return {
    month,
    from: `${month}-01`,
    to: `${month}-${String(last).padStart(2, "0")}`,
    closed: false,
    reasons: [],
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [{ ...PENDING_INVOICE, occurred_on: `${month}-05` }],
    cuentas_por_pagar: [],
    currencies: [{ currency: "DOP", income_before_itbis: "48500.00", expense_before_itbis: "12300.00", net_result: "36200.00", itbis_owed: "6516.00" }],
  };
}

export const OPEN_ITEMS_WIRE = {
  cuentas_por_cobrar: { count: 1, totals: [{ currency: "DOP", total_minor: PENDING_INVOICE.total_minor }], items: [PENDING_INVOICE] },
  cuentas_por_pagar: { count: 0, totals: [], items: [] },
};
