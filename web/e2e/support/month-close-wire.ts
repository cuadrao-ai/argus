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
  due_on: null,
};

/** The server's day for these wires: the machine's own, so the month the browser asks for first is the server's month. */
function serverToday(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-${String(now.getDate()).padStart(2, "0")}`;
}

const BY_STATUS = {
  invoices: { pendiente: { count: 1, before_itbis_minor: 5_000_000 }, cobrado: { count: 0, before_itbis_minor: 0 } },
  receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } },
};

export function monthCloseWire(month: string) {
  const [year, index] = month.split("-").map(Number);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return {
    month,
    today: serverToday(),
    from: `${month}-01`,
    to: `${month}-${String(last).padStart(2, "0")}`,
    closed: false,
    reasons: [],
    earliest_month: month,
    payment_methods: ["efectivo", "transferencia", "tarjeta", "credito", "otro"],
    dgii_forms: { "606": "needs_review", "607": "needs_review" },
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [{ ...PENDING_INVOICE, occurred_on: `${month}-05` }],
    cuentas_por_pagar: [],
    currencies: [{
      currency: "DOP",
      income_before_itbis_minor: 4850000, income_before_itbis: "48500.00",
      expense_before_itbis_minor: 1230000, expense_before_itbis: "12300.00",
      net_result_minor: 3620000, net_result: "36200.00",
      itbis_owed_minor: 651600, itbis_owed: "6516.00",
      itbis_cobrado_minor: 0, itbis_cobrado: "0.00",
      by_status: BY_STATUS,
      net_result_final: false,
    }],
  };
}

export const OPEN_ITEMS_WIRE = {
  today: serverToday(),
  cuentas_por_cobrar: { count: 1, totals: [{ currency: "DOP", total_minor: PENDING_INVOICE.total_minor }], overdue: { count: 0, totals: [] }, items: [PENDING_INVOICE] },
  cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] },
};
