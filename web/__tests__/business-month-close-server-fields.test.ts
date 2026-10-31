import { describe, expect, test } from "bun:test";
import {
  createHttpMonthCloseClient,
  loadCurrentMonth,
  joinCurrencyList,
  monthCloseNetDisplay,
  monthClosePendingRateCurrencies,
  monthPickerMonths,
  readMonthCloseWire,
  readOpenItemsWire,
  canStepMonth,
} from "../lib/business-month-close";

function block(currency: string, extra: Record<string, unknown> = {}) {
  return {
    currency,
    income_before_itbis_minor: 400000,
    expense_before_itbis_minor: 150000,
    net_result_minor: 250000,
    itbis_owed_minor: 18000,
    itbis_cobrado_minor: 45000,
    by_status: { invoices: { pendiente: { count: 2, before_itbis_minor: 0 }, cobrado: { count: 1, before_itbis_minor: 0 } }, receipts: { pendiente: { count: 1, before_itbis_minor: 0 }, pagado: { count: 0, before_itbis_minor: 0 } } },
    net_result_final: false,
    ...extra,
  };
}

function month(value: string, extra: Record<string, unknown> = {}) {
  const [year, index] = value.split("-").map(Number);
  const last = new Date(Date.UTC(year, index, 0)).getUTCDate();
  return {
    month: value,
    today: "2026-11-01",
    from: `${value}-01`,
    to: `${value}-${String(last).padStart(2, "0")}`,
    closed: true,
    reasons: [],
    earliest_month: "2026-08",
    payment_methods: ["efectivo", "transferencia", "tarjeta", "credito", "otro"],
    dgii_forms: { "606": "prepared_candidate", "607": "needs_review" },
    currencies: [block("DOP")],
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [],
    cuentas_por_pagar: [],
    ...extra,
  };
}

describe("month close reads the server's own fields", () => {
  test("today, earliest_month, payment_methods and each form's status come from the body", () => {
    const snapshot = readMonthCloseWire(month("2026-11"));
    expect(snapshot.today).toBe("2026-11-01");
    expect(snapshot.earliest_month).toBe("2026-08");
    expect(snapshot.payment_methods).toEqual(["efectivo", "transferencia", "tarjeta", "credito", "otro"]);
    expect(snapshot.dgii_forms).toEqual({ "606": "prepared_candidate", "607": "needs_review" });
  });

  test("an older server without the fields leaves each one unknown, never a guess", () => {
    const older: Record<string, unknown> = month("2026-10");
    for (const field of ["today", "earliest_month", "payment_methods", "dgii_forms"]) delete older[field];
    const snapshot = readMonthCloseWire({ ...older, currencies: [{ currency: "DOP", net_result_minor: 100 }] });
    expect(snapshot.today).toBeNull();
    expect(snapshot.earliest_month).toBeNull();
    expect(snapshot.payment_methods).toBeNull();
    expect(snapshot.dgii_forms).toBeNull();
    expect(snapshot.figures[0].net_result_final).toBeNull();
    expect(snapshot.figures[0].itbis_cobrado).toBeNull();
    expect(snapshot.figures[0].pending_count).toBeNull();
  });

  test("a form word the web does not know is unknown for that form only", () => {
    expect(readMonthCloseWire(month("2026-10", { dgii_forms: { "606": "sent_to_dgii", "607": "no_operations" } })).dgii_forms).toEqual({ "606": null, "607": "no_operations" });
  });

  test("each currency block carries its ITBIS cobrado, its pending count and whether its net is final", () => {
    const snapshot = readMonthCloseWire(month("2026-10", { currencies: [block("DOP"), block("USD", { itbis_cobrado_minor: 216, net_result_final: true })] }));
    expect(snapshot.figures.map((figures) => [figures.currency, figures.itbis_cobrado, figures.pending_count, figures.net_result_final])).toEqual([
      ["DOP", "450.00", 3, false],
      ["USD", "2.16", 3, true],
    ]);
  });
});

describe("the net follows net_result_final", () => {
  test("false withholds the figure and says how many documents of that currency are left to mark", () => {
    const [figures] = readMonthCloseWire(month("2026-10")).figures;
    expect(monthCloseNetDisplay(figures)).toEqual({ state: "pending", pending_count: 3, reason: "documents" });
  });

  test("false with a count of zero is a rate still pending, not zero documents", () => {
    const [figures] = readMonthCloseWire(month("2026-10", {
      currencies: [block("USD", {
        net_result_final: false,
        by_status: {
          invoices: { pendiente: { count: 0, before_itbis_minor: 0 }, cobrado: { count: 1, before_itbis_minor: 0 } },
          receipts: { pendiente: { count: 0, before_itbis_minor: 0 }, pagado: { count: 1, before_itbis_minor: 0 } },
        },
      })],
    })).figures;
    expect(figures.pending_count).toBe(0);
    expect(monthCloseNetDisplay(figures)).toEqual({ state: "pending", pending_count: 0, reason: "pending_rate" });
  });

  test("pending rate codes are the readable zero-count blocks, in alphabetical order", () => {
    const block = (currency: string, pending_count: number | null, net_result_final: boolean | null) => ({
      currency,
      net_before_itbis: "1.00",
      net_result_final,
      pending_count,
    });
    const codes = monthClosePendingRateCurrencies([
      block("USD", 0, false),
      block("eur", 0, false),
      block("DOP", 0, false),
      block("GBP", 2, false),
      block("JPY", 0, true),
      block("US", 0, false),
    ]);
    expect(codes).toEqual(["DOP", "USD"]);
    expect(joinCurrencyList(codes, "y")).toBe("DOP y USD");
    expect(joinCurrencyList(["DOP", "EUR", "USD"], "y")).toBe("DOP, EUR y USD");
    expect(joinCurrencyList(["EUR", "USD"], "y")).toBe("EUR y USD");
    expect(joinCurrencyList(["EUR", "USD"], "and")).toBe("EUR and USD");
    expect(joinCurrencyList(["USD"], "y")).toBe("USD");
    expect(joinCurrencyList([], "y")).toBe("");
  });

  test("true shows the figure, whatever the web holds about the month's documents", () => {
    const [figures] = readMonthCloseWire(month("2026-10", { currencies: [block("DOP", { net_result_final: true })] })).figures;
    expect(monthCloseNetDisplay(figures)).toEqual({ state: "final", net_before_itbis: "2500.00" });
  });

  test("absent is unknown, not final", () => {
    const [figures] = readMonthCloseWire(month("2026-10", { currencies: [{ currency: "DOP", net_result_minor: 250000 }] })).figures;
    expect(monthCloseNetDisplay(figures)).toEqual({ state: "pending", pending_count: 0, reason: "unknown" });
  });
});

describe("open items carry the server's today and overdue", () => {
  const wire = {
    today: "2026-11-01",
    cuentas_por_cobrar: { count: 140, totals: [{ currency: "DOP", total_minor: 9000000 }], overdue: { count: 120, totals: [{ currency: "DOP", total_minor: 1230000 }, { currency: "USD", total_minor: 5000 }] }, items: [] },
    cuentas_por_pagar: { count: 0, totals: [], overdue: { count: 0, totals: [] }, items: [] },
  };

  test("overdue is the server's count and its per-currency totals, over every item and not only the page", () => {
    const open = readOpenItemsWire(wire);
    expect(open.today).toBe("2026-11-01");
    expect(open.cuentas_por_cobrar.overdue).toEqual({ count: 120, totals: [{ currency: "DOP", total: "12300.00" }, { currency: "USD", total: "50.00" }] });
    expect(open.cuentas_por_pagar.overdue).toEqual({ count: 0, totals: [] });
  });

  test("an older server without overdue leaves it unknown", () => {
    const open = readOpenItemsWire({ cuentas_por_cobrar: { count: 0, totals: [], items: [] }, cuentas_por_pagar: { count: 0, totals: [], items: [] } });
    expect(open.today).toBeNull();
    expect(open.cuentas_por_cobrar.overdue).toBeNull();
  });
});

describe("the current month is the server's", () => {
  test("a browser one day behind the server still reads the server's month", async () => {
    const asked: string[] = [];
    const client = createHttpMonthCloseClient(async (path) => {
      const value = new URLSearchParams(path.split("?")[1]).get("month")!;
      asked.push(value);
      return month(value);
    });
    const snapshot = await loadCurrentMonth(client, "own", "2026-10");
    expect(snapshot.month).toBe("2026-11");
    expect(asked).toEqual(["2026-10", "2026-11"]);
  });

  test("a browser on the server's month asks once", async () => {
    const asked: string[] = [];
    const client = createHttpMonthCloseClient(async (path) => {
      const value = new URLSearchParams(path.split("?")[1]).get("month")!;
      asked.push(value);
      return month(value);
    });
    await loadCurrentMonth(client, "own", "2026-11");
    expect(asked).toEqual(["2026-11"]);
  });
});

describe("earliest_month bounds the month picker", () => {
  test("months before the earliest are not offered, and the arrow stops there", () => {
    const months = monthPickerMonths("2026-11", "2026-08");
    expect(months[0]).toEqual({ month: "2026-08", selectable: true });
    expect(canStepMonth("2026-08", -1, "2026-11", "2026-08")).toBe(false);
    expect(canStepMonth("2026-09", -1, "2026-11", "2026-08")).toBe(true);
  });

  test("supported history crosses the year boundary and ends at the current month", () => {
    expect(monthPickerMonths("2026-02", "2025-11")).toEqual([
      { month: "2025-11", selectable: true },
      { month: "2025-12", selectable: true },
      { month: "2026-01", selectable: true },
      { month: "2026-02", selectable: true },
    ]);
  });

  test.each(["2026-12", "invalid"])("an unsupported earliest month %s offers only the current month", (earliest) => {
    expect(monthPickerMonths("2026-11", earliest)).toEqual([{ month: "2026-11", selectable: true }]);
  });

  test("a Business with no documents yet offers only the current month, not a 24-month guess", () => {
    const months = monthPickerMonths("2026-11", null);
    expect(months).toEqual([{ month: "2026-11", selectable: true }]);
    expect(canStepMonth("2026-11", -1, "2026-11", null)).toBe(false);
  });
});

describe("a one-tap mark sends a method the server lists", () => {
  test("the PATCH carries the settlement the view passes: the server's day and its listed method", async () => {
    const sent: { path: string; body: unknown }[] = [];
    const client = createHttpMonthCloseClient(async (path, init) => {
      sent.push({ path, body: init?.body ? JSON.parse(String(init.body)) : null });
      return { activity_id: "act-1", document_kind: "invoice", status: "cobrado", settled_on: "2026-11-01", payment_method: "otro", changed: true };
    });
    await client.markCobrado("act-1", undefined, { settled_on: "2026-11-01", payment_method: "otro" });
    expect(sent).toEqual([{ path: "/business/month-close/documents/act-1", body: { status: "cobrado", settled_on: "2026-11-01", payment_method: "otro" } }]);
  });
});
