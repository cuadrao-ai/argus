import { describe, expect, test } from "bun:test";
import {
  createMockMonthCloseClient,
  currenciesInOrder,
  currencyShown,
  monthCloseNetDisplay,
  openItemsOverdue,
  readMonthCloseWire,
  readOpenItemsWire,
  type MonthCloseDocument,
} from "../lib/business-month-close";

const now = new Date(2026, 9, 18);

function block(currency: string, minor: { income: number; expense: number; itbisOwed: number }) {
  return {
    currency,
    income_before_itbis_minor: minor.income,
    expense_before_itbis_minor: minor.expense,
    net_result_minor: minor.income - minor.expense,
    itbis_owed_minor: minor.itbisOwed,
  };
}

function line(id: string, kind: "invoice" | "receipt", currency: string | undefined, totalMinor: number, itbisMinor: number | null, extra: Record<string, unknown> = {}) {
  return {
    activity_id: id,
    document_kind: kind,
    ...(currency === undefined ? {} : { currency }),
    occurred_on: "2026-10-05",
    total_minor: totalMinor,
    itbis_minor: itbisMinor,
    status: "pendiente",
    counterparty: `Cliente ${id}`,
    due_on: null,
    ...extra,
  };
}

function wire(currencies: unknown[], lists: Record<string, unknown[]> = {}) {
  return { month: "2026-10", from: "2026-10-01", to: "2026-10-31", closed: true, reasons: [], currencies, missing_rnc: [], missing_ncf: [], cuentas_por_cobrar: [], cuentas_por_pagar: [], ...lists };
}

function document(partial: Partial<MonthCloseDocument> & Pick<MonthCloseDocument, "id" | "currency" | "status">): MonthCloseDocument {
  return { kind: "invoice", counterparty: partial.id, occurred_on: "2026-10-02", due_on: null, amount: "1.00", itbis: null, rnc: "131-99988-8", ncf: "B0100000001", ecf: null, ...partial };
}

describe("month close keeps every currency the server sends", () => {
  test("a USD-only month keeps its own figures, not unknown", () => {
    const snapshot = readMonthCloseWire(wire([block("USD", { income: 120000, expense: 2400, itbisOwed: 21600 })]));
    expect(snapshot.figures).toEqual([
      { currency: "USD", income_before_itbis: "1200.00", expense_before_itbis: "24.00", net_before_itbis: "1176.00", itbis_owed: "216.00" },
    ]);
  });

  test("a DOP and USD month keeps one block per currency, in the server's order", () => {
    const snapshot = readMonthCloseWire(wire([block("DOP", { income: 400000, expense: 150000, itbisOwed: 18000 }), block("USD", { income: 120000, expense: 2400, itbisOwed: 21600 })]));
    expect(snapshot.figures.map((figures) => [figures.currency, figures.net_before_itbis])).toEqual([["DOP", "2500.00"], ["USD", "1176.00"]]);
  });

  test("a figure the block does not send is unknown, never zero", () => {
    const snapshot = readMonthCloseWire(wire([{ currency: "DOP", income_before_itbis_minor: 1000 }]));
    expect(snapshot.figures).toEqual([{ currency: "DOP", income_before_itbis: "10.00", expense_before_itbis: null, net_before_itbis: null, itbis_owed: null }]);
  });

  test("zero and three decimal currencies read exactly from minor units", () => {
    const snapshot = readMonthCloseWire(wire(
      [block("BHD", { income: 1234567, expense: 1234572, itbisOwed: 50 }), block("JPY", { income: 1500, expense: 0, itbisOwed: 0 })],
      { cuentas_por_cobrar: [line("yen", "invoice", "JPY", 1500, null)], cuentas_por_pagar: [line("dinar", "receipt", "BHD", 1050, 50)] },
    ));
    const [bhd, jpy] = snapshot.figures;
    expect(bhd).toEqual({ currency: "BHD", income_before_itbis: "1234.567", expense_before_itbis: "1234.572", net_before_itbis: "-0.005", itbis_owed: "0.050" });
    expect(jpy.income_before_itbis).toBe("1500");
    expect(snapshot.documents.map((item) => [item.id, item.amount, item.itbis])).toEqual([["yen", "1500", null], ["dinar", "1.050", "0.050"]]);
    const open = readOpenItemsWire({
      cuentas_por_cobrar: { count: 1, totals: [{ currency: "JPY", total_minor: 1500, total: "1500" }], items: [line("yen", "invoice", "JPY", 1500, null)] },
      cuentas_por_pagar: { count: 1, totals: [{ currency: "BHD", total_minor: 1050, total: "1.050" }], items: [line("dinar", "receipt", "BHD", 1050, 50)] },
    });
    expect(open.cuentas_por_cobrar.totals).toEqual([{ currency: "JPY", total: "1500" }]);
    expect(open.cuentas_por_pagar.totals).toEqual([{ currency: "BHD", total: "1.050" }]);
  });

  test("a line with no currency stays unknown and is never read as DOP", () => {
    const snapshot = readMonthCloseWire(wire([], { cuentas_por_cobrar: [line("bare", "invoice", undefined, 5000, 900)] }));
    expect(snapshot.documents[0]).toMatchObject({ id: "bare", currency: null, amount: null, itbis: null });
    const open = readOpenItemsWire({
      cuentas_por_cobrar: { count: 1, totals: [], items: [line("bare", "invoice", undefined, 5000, null)] },
      cuentas_por_pagar: { count: 0, totals: [], items: [] },
    });
    expect(open.cuentas_por_cobrar.items[0]).toMatchObject({ currency: null, amount: null });
  });

  test("a missing counterparty stays missing, so the screen names it in the person's language", () => {
    const snapshot = readMonthCloseWire(wire([], { cuentas_por_cobrar: [line("nameless", "invoice", "DOP", 5000, null, { counterparty: null })] }));
    expect(snapshot.documents[0].counterparty).toBeNull();
  });
});

describe("the net waits only on its own currency", () => {
  test("a pending USD document does not hold back the DOP net", () => {
    const documents = [document({ id: "dop", currency: "DOP", status: "cobrado" }), document({ id: "usd", currency: "USD", status: "pendiente" })];
    expect(monthCloseNetDisplay(documents, [], "100.00", "DOP")).toEqual({ state: "final", net_before_itbis: "100.00" });
    expect(monthCloseNetDisplay(documents, [], "50.00", "USD")).toEqual({ state: "pending", pending_count: 1, reason: "documents" });
  });

  test("a pending document with no currency could be any currency, so it holds back each net", () => {
    const documents = [document({ id: "bare", currency: null, status: "pendiente" })];
    expect(monthCloseNetDisplay(documents, [], "100.00", "DOP").state).toBe("pending");
    expect(monthCloseNetDisplay(documents, [], "50.00", "USD").state).toBe("pending");
  });
});

describe("which currency the figures show", () => {
  test("the Business currency leads, then the server's order", () => {
    expect(currenciesInOrder(["DOP", "USD"], "USD")).toEqual(["USD", "DOP"]);
    expect(currenciesInOrder(["DOP", "USD"], null)).toEqual(["DOP", "USD"]);
    expect(currenciesInOrder(["DOP", "USD"], "CAD")).toEqual(["DOP", "USD"]);
  });

  test("the person's choice when the month has it, else the Business currency, else the first the server sends", () => {
    expect(currencyShown(["DOP", "USD"], "DOP", "USD")).toBe("USD");
    expect(currencyShown(["DOP", "USD"], "DOP", "EUR")).toBe("DOP");
    expect(currencyShown(["DOP", "USD"], "USD", null)).toBe("USD");
    expect(currencyShown(["USD"], "DOP", null)).toBe("USD");
    expect(currencyShown([], "DOP", "USD")).toBeNull();
  });
});

describe("overdue keeps each currency's own digits", () => {
  test("yen and dinars add up exactly and apart", () => {
    const overdue = (id: string, currency: string, amount: string) => document({ id, currency, amount, status: "pendiente", due_on: "2026-10-01" });
    const list = { count: 3, totals: [], items: [overdue("a", "JPY", "1500"), overdue("b", "JPY", "25"), overdue("c", "BHD", "1.005")] };
    expect(openItemsOverdue(list, "2026-10-18").totals).toEqual([{ currency: "JPY", total: "1525" }, { currency: "BHD", total: "1.005" }]);
  });
});

describe("the sample month holds a second currency", () => {
  test("by default the sample books hold pesos alone", async () => {
    const client = createMockMonthCloseClient({ now });
    expect((await client.load("2026-10")).figures.map((figures) => figures.currency)).toEqual(["DOP"]);
  });

  test("with dollars, the open month has DOP and USD blocks, each from its own documents; the month before has DOP alone", async () => {
    const client = createMockMonthCloseClient({ now, dollars: true });
    const current = await client.load("2026-10");
    expect(current.figures.map((figures) => figures.currency)).toEqual(["DOP", "USD"]);
    expect(current.figures[0]).toMatchObject({ income_before_itbis: "58400.00", expense_before_itbis: "9600.00" });
    expect(current.figures[1]).toEqual({ currency: "USD", income_before_itbis: "1200.00", expense_before_itbis: "24.00", net_before_itbis: "1176.00", itbis_owed: "216.00" });
    const previous = await client.load("2026-09");
    expect(previous.figures.map((figures) => figures.currency)).toEqual(["DOP"]);
  });
});
