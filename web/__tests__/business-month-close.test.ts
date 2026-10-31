import { describe, expect, test } from "bun:test";
import {
  MonthCloseError,
  calendarDay,
  calendarMonthOf,
  canCloseMonth,
  documentOverdue,
  dueDistance,
  canStepMonth,
  closeGate,
  createHttpMonthCloseClient,
  createMockMonthCloseClient,
  fiscalNumberPresent,
  formatMonthLabel,
  monthCloseBlockers,
  monthCloseLoadRequest,
  monthCloseNetDisplay,
  monthCloseReopenRequest,
  monthCloseRequestPath,
  monthCloseSampleDocuments,
  monthCloseSettlementRequest,
  monthCloseFiguresFrom,
  monthPickerFloor,
  monthPickerMonths,
  openItemsFrom,
  openItemsHeaderCurrency,
  openItemsInDueOrder,
  openItemsRequest,
  openItemsTotalsInOrder,
  overdueTotalsInOrder,
  OPEN_ITEMS_CAP,
  readOpenItemsWire,
  readMonthCloseWire,
  rncPresent,
  statementMissingBlocker,
  unmatchedCharges,
  shiftMonthKey,
  type MonthCloseDocument,
} from "../lib/business-month-close";

const now = new Date(2026, 9, 18);

function document(partial: Pick<MonthCloseDocument, "id" | "kind" | "amount" | "itbis" | "status"> & Partial<MonthCloseDocument>): MonthCloseDocument {
  return {
    currency: "DOP",
    counterparty: partial.id,
    occurred_on: "2026-10-01",
    due_on: null,
    rnc: "131-99988-8",
    ncf: "B0100000001",
    ecf: null,
    ...partial,
  };
}

describe("month close money", () => {
  test("net is income minus expenses before ITBIS, and ITBIS owed is the tax difference", () => {
    const [summary] = monthCloseFiguresFrom([
      document({ id: "invoice", kind: "invoice", amount: "118.00", itbis: "18.00", status: "cobrado" }),
      document({ id: "receipt", kind: "receipt", amount: "59.00", itbis: null, status: "pagado" }),
    ]);
    expect(summary).toEqual({
      currency: "DOP",
      income_before_itbis: "100.00",
      expense_before_itbis: "59.00",
      net_before_itbis: "41.00",
      itbis_owed: "18.00",
      itbis_cobrado: "18.00",
      net_result_final: true,
      pending_count: 0,
    });
  });

  test("a missing ITBIS counts as zero and is not invented from the total", () => {
    const [summary] = monthCloseFiguresFrom([
      document({ id: "invoice", kind: "invoice", amount: "10.00", itbis: null, status: "pendiente" }),
      document({ id: "receipt", kind: "receipt", amount: "40.00", itbis: "5.00", status: "pendiente" }),
    ]);
    expect(summary.net_before_itbis).toBe("-25.00");
    expect(summary.itbis_owed).toBe("-5.00");
  });

  test("the sample month matches the hand totals, including a receipt with no stated ITBIS", () => {
    const documents = monthCloseSampleDocuments(now);
    const current = documents.filter((item) => item.occurred_on.startsWith("2026-10"));
    const previous = documents.filter((item) => item.occurred_on.startsWith("2026-09"));
    expect(monthCloseFiguresFrom(current)[0]).toEqual({
      currency: "DOP",
      income_before_itbis: "58400.00",
      expense_before_itbis: "9600.00",
      net_before_itbis: "48800.00",
      itbis_owed: "7902.00",
      itbis_cobrado: "6120.00",
      net_result_final: false,
      pending_count: 4,
    });
    expect(monthCloseFiguresFrom(previous)).toEqual([{
      currency: "DOP",
      income_before_itbis: "17000.00",
      expense_before_itbis: "2800.00",
      net_before_itbis: "14200.00",
      itbis_owed: "2556.00",
      itbis_cobrado: "2160.00",
      net_result_final: false,
      pending_count: 2,
    }]);
  });
});

describe("month close net honesty", () => {
  test("a block that is not final withholds the net number", () => {
    const display = monthCloseNetDisplay({ net_before_itbis: "41.00", net_result_final: false, pending_count: 1 });
    expect(display).toEqual({ state: "pending", pending_count: 1, reason: "documents" });
    expect(display).not.toHaveProperty("net_before_itbis");
  });

  test("the sample month stays pending, and a settled month shows the number", () => {
    const current = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-10"));
    expect(monthCloseNetDisplay(monthCloseFiguresFrom(current)[0])).toEqual({ state: "pending", pending_count: 4, reason: "documents" });
    const settled = current.map((item) => ({ ...item, status: item.kind === "invoice" ? "cobrado" as const : "pagado" as const }));
    expect(monthCloseNetDisplay(monthCloseFiguresFrom(settled)[0])).toEqual({ state: "final", net_before_itbis: "48800.00" });
  });
});

describe("month close blockers and the close gate", () => {
  test("a missing RNC or NCF blocks the month; a pending document with both does not; an e-CF counts as the comprobante", () => {
    const documents = [
      document({ id: "ready", kind: "invoice", amount: "100.00", itbis: "18.00", status: "cobrado" }),
      document({ id: "electronic", kind: "invoice", amount: "100.00", itbis: "18.00", status: "cobrado", ncf: null, ecf: "E310000000012" }),
      document({ id: "pending", kind: "receipt", amount: "10.00", itbis: "0.00", status: "pendiente" }),
      document({ id: "zeros", kind: "invoice", amount: "10.00", itbis: "0.00", status: "cobrado", rnc: "000-00000-0" }),
      document({ id: "blank", kind: "receipt", amount: "10.00", itbis: null, status: "pagado", ncf: null, ecf: null }),
    ];
    expect(rncPresent("000-00000-0")).toBe(false);
    expect(rncPresent("131-99988-8")).toBe(true);
    expect(fiscalNumberPresent({ ncf: null, ecf: "E310000000012" })).toBe(true);
    expect(fiscalNumberPresent({ ncf: "B02", ecf: null })).toBe(false);
    expect(monthCloseBlockers(documents).map((blocker) => blocker.id)).toEqual([
      "blank:missing_ncf",
      "zeros:missing_rnc",
    ]);
    expect(canCloseMonth({ month: "2026-10", closed_at: null, unreviewed_movements: 0, documents })).toEqual({ ok: false, reason: "blockers" });
    const pendingOnly = [document({ id: "pending", kind: "receipt", amount: "10.00", itbis: "0.00", status: "pendiente" })];
    expect(monthCloseBlockers(pendingOnly)).toEqual([]);
    expect(canCloseMonth({ month: "2026-10", closed_at: null, unreviewed_movements: 0, documents: pendingOnly })).toEqual({ ok: true, month: "2026-10" });
  });

  test("the sample month lists the documents missing an RNC or a comprobante, and not the pending ones that have both", () => {
    const current = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-10"));
    const ids = monthCloseBlockers(current).map((blocker) => blocker.id);
    expect(ids).toContain("inv-farmacia:missing_rnc");
    expect(ids).toContain("inv-caribe:missing_ncf");
    expect(ids).toContain("rcpt-transporte:missing_rnc");
    expect(ids).toContain("rcpt-transporte:missing_ncf");
    expect(ids).not.toContain("inv-taller:missing_ncf");
    expect(ids.some((id) => id.endsWith(":pending"))).toBe(false);
  });

  test("close stays shut until the window is one calendar month with no fiscal blockers", () => {
    const open = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-10"));
    const previous = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-09"));
    expect(canCloseMonth({ month: "2026-10", closed_at: null, unreviewed_movements: 0, documents: open })).toEqual({ ok: false, reason: "blockers" });
    expect(canCloseMonth({ month: "2026-09", closed_at: null, unreviewed_movements: 0, documents: previous })).toEqual({ ok: true, month: "2026-09" });
    expect(canCloseMonth({ month: null, closed_at: null, unreviewed_movements: 0, documents: [] })).toEqual({ ok: false, reason: "not_calendar_month" });
    expect(canCloseMonth({ month: "2026-09", closed_at: "2026-10-01T12:00:00.000Z", unreviewed_movements: 0, documents: [] })).toEqual({ ok: false, reason: "closed" });
    expect(closeGate).toBe(canCloseMonth);
    expect(calendarMonthOf("2026-10-01", null, "2026-10-18")).toBe("2026-10");
    expect(calendarMonthOf("2026-09-01", "2026-09-30", "2026-10-18")).toBe("2026-09");
    expect(calendarMonthOf("2026-09-19", null, "2026-10-18")).toBeNull();
    expect(calendarMonthOf("2000-01-01", null, "2026-10-18")).toBeNull();
    expect(calendarMonthOf("2026-08-01", "2026-08-15", "2026-10-18")).toBeNull();
    expect(canCloseMonth({ month: "2026-09", closed_at: null, unreviewed_movements: 0, documents: [] })).toEqual({ ok: true, month: "2026-09" });
  });

  test("an early month day still parses, and a mismatched status does not", () => {
    const line = { activity_id: "inv-1", document_kind: "invoice", currency: "DOP", counterparty: "Colmado Don Luis", occurred_on: "2026-10-01", total_minor: 1000, itbis_minor: null, status: "pendiente", due_on: null };
    expect(readMonthCloseWire({ ...wire, reasons: [], missing_rnc: [line] }).documents[0]?.amount).toBe("10.00");
    expect(() => readMonthCloseWire({ ...wire, reasons: [], missing_rnc: [{ ...line, status: "pagado" }] })).toThrow(MonthCloseError);
  });
});

describe("month close mock client", () => {
  test("a month with RNC and NCF closes while items are still pending", async () => {
    const client = createMockMonthCloseClient({ now });
    const lastMonth = "2026-09";
    let snapshot = await client.load(lastMonth);
    expect(snapshot.month).toBe("2026-09");
    expect(canCloseMonth(snapshot)).toEqual({ ok: true, month: "2026-09" });
    expect(monthCloseNetDisplay(snapshot.figures[0]).state).toBe("pending");
    await expect(client.markPagado("inv-luna")).rejects.toMatchObject({ code: "invalid_status" });
    await client.markCobrado("inv-luna");
    await client.markPagado("rcpt-rosa");
    snapshot = await client.load(lastMonth);
    expect(canCloseMonth(snapshot)).toEqual({ ok: true, month: "2026-09" });
    expect(monthCloseNetDisplay(snapshot.figures[0])).toEqual({ state: "final", net_before_itbis: "14200.00" });
    const closed = await client.closeMonth("2026-09");
    expect(closed.closed_at).toBeTruthy();
    expect(closed.documents.every((item) => item.status !== "pendiente")).toBe(true);
    await expect(client.markCobrado("inv-luna")).rejects.toMatchObject({ code: "closed" });
    await expect(client.closeMonth("2026-10")).rejects.toMatchObject({ code: "blockers" });
  });

  test("a mark in one Business does not change another Business", async () => {
    const client = createMockMonthCloseClient({ now });
    const lastMonth = "2026-09";
    await client.markCobrado("inv-luna", "grant-a");
    const other = await client.load(lastMonth, "grant-b");
    expect(other.documents.find((item) => item.id === "inv-luna")?.status).toBe("pendiente");
    const same = await client.load(lastMonth, "grant-a");
    expect(same.documents.find((item) => item.id === "inv-luna")?.status).toBe("cobrado");
  });

  test("a failed mark leaves the stored status untouched", async () => {
    const client = createMockMonthCloseClient({ now, failIds: ["inv-taller"] });
    await expect(client.markCobrado("inv-taller")).rejects.toMatchObject({ code: "unavailable" });
    const snapshot = await client.load("2026-10");
    expect(snapshot.documents.find((item) => item.id === "inv-taller")?.status).toBe("pendiente");
  });

  test("load asks for the month, and the path is GET ?month=", async () => {
    const client = createMockMonthCloseClient({ now });
    const snapshot = await client.load("2026-09");
    expect(snapshot.month).toBe("2026-09");
    expect(snapshot.earliest_month).toBe("2026-09");
    expect(monthCloseRequestPath("2026-10")).toBe("/business/month-close?month=2026-10");
    expect(() => monthCloseRequestPath("2026-10-01")).toThrow(MonthCloseError);
  });
});

describe("month switcher", () => {
  test("the label is the Spanish month name and the year", () => {
    expect(formatMonthLabel("2026-10", "es-419")).toBe("Octubre 2026");
    expect(formatMonthLabel("2026-01", "es-419")).toBe("Enero 2026");
  });

  test("previous and next step across a year, and next stops on the current month", () => {
    expect(shiftMonthKey("2026-01", -1)).toBe("2025-12");
    expect(shiftMonthKey("2025-12", 1)).toBe("2026-01");
    expect(canStepMonth("2026-10", 1, "2026-10")).toBe(false);
    expect(canStepMonth("2026-09", 1, "2026-10")).toBe(true);
    expect(canStepMonth("2026-01", -1, "2026-10", "2025-06")).toBe(true);
    expect(monthPickerFloor("2026-10", null)).toBe("2026-10");
    expect(monthPickerFloor("2026-10", "2020-03")).toBe("2020-03");
    expect(monthPickerMonths("2026-10", "2026-09")).toEqual([
      { month: "2026-09", selectable: true },
      { month: "2026-10", selectable: true },
    ]);
  });

  test("a pending document due before today is overdue, and a settled one is not", () => {
    const today = calendarDay(now);
    expect(today).toBe("2026-10-18");
    expect(dueDistance("2026-10-02", today)).toEqual({ direction: "past", days: 16 });
    expect(dueDistance("2026-10-18", today)).toEqual({ direction: "today", days: 0 });
    expect(dueDistance("2026-10-28", today)).toEqual({ direction: "future", days: 10 });
    const farmacia = monthCloseSampleDocuments(now).find((item) => item.id === "inv-farmacia");
    const taller = monthCloseSampleDocuments(now).find((item) => item.id === "inv-taller");
    const colmado = monthCloseSampleDocuments(now).find((item) => item.id === "inv-colmado");
    expect(farmacia?.due_on).toBe("2026-10-02");
    expect(documentOverdue(farmacia!, today)).toBe(true);
    expect(documentOverdue(taller!, today)).toBe(false);
    expect(documentOverdue(colmado!, today)).toBe(false);
    expect(documentOverdue({ status: "pendiente", due_on: null }, today)).toBe(false);
    const line = { activity_id: "inv-1", document_kind: "invoice", currency: "DOP", counterparty: "Farmacia Central", occurred_on: "2026-10-01", due_on: "2026-10-02", total_minor: 1000, itbis_minor: null, status: "pendiente" };
    expect(readMonthCloseWire({ ...wire, reasons: [], missing_rnc: [line] }).documents[0]?.due_on).toBe("2026-10-02");
    expect(() => readMonthCloseWire({ ...wire, reasons: [], missing_rnc: [{ ...line, due_on: "October" }] })).toThrow(MonthCloseError);
  });
});

describe("future statement blockers stay in the gate and out of the lock", () => {
  test("a missing statement does not lock the month, and an unknown net is never a zero", () => {
    const documents = [document({ id: "ready", kind: "invoice", amount: "100.00", itbis: "18.00", status: "cobrado" })];
    expect(statementMissingBlocker.kind).toBe("statement_missing");
    expect(canCloseMonth({ month: "2026-10", closed_at: null, unreviewed_movements: 0, documents, blockers: [statementMissingBlocker] })).toEqual({ ok: true, month: "2026-10" });
    expect(unmatchedCharges(3)).toEqual({ kind: "unmatched_charges", count: 3 });
    expect(() => unmatchedCharges(0)).toThrow(MonthCloseError);
    expect(monthCloseNetDisplay({ net_before_itbis: null, net_result_final: true, pending_count: 0 })).toEqual({ state: "pending", pending_count: 0, reason: "unknown" });
    expect(JSON.stringify(monthCloseNetDisplay({ net_before_itbis: "100.00", net_result_final: null, pending_count: null }))).not.toContain("0.00");
  });
});

const wire = {
  month: "2026-10",
  from: "2026-10-01",
  to: "2026-10-31",
  closed: false,
  reasons: [{ code: "missing_rnc", activity_id: "act-1", document_kind: "invoice" }],
  currencies: [],
  missing_rnc: [{ activity_id: "act-1", document_kind: "invoice", currency: "DOP", occurred_on: "2026-10-02", total_minor: 640000, before_itbis_minor: 640000, itbis_minor: null, status: "pendiente" }],
  missing_ncf: [],
  cuentas_por_cobrar: [],
  cuentas_por_pagar: [],
};

describe("month close HTTP contract", () => {
  test("load is GET with month only, marks are PATCH with the settlement body, and close sends nothing", async () => {
    expect(monthCloseLoadRequest("2026-10")).toEqual({ method: "GET", path: "/business/month-close?month=2026-10" });
    expect(monthCloseSettlementRequest("act-1", "cobrado", { settled_on: "2026-10-18", payment_method: "otro" })).toEqual({
      method: "PATCH",
      path: "/business/month-close/documents/act-1",
      body: { status: "cobrado", settled_on: "2026-10-18", payment_method: "otro" },
    });
    expect(monthCloseSettlementRequest("act-2", "pagado", { settled_on: "2026-10-18", payment_method: "transferencia" }).body).toEqual({
      status: "pagado",
      settled_on: "2026-10-18",
      payment_method: "transferencia",
    });
    const calls: { path: string; method: string; body?: string }[] = [];
    const client = createHttpMonthCloseClient(async (path, init) => {
      calls.push({ path, method: init?.method ?? "GET", body: typeof init?.body === "string" ? init.body : undefined });
      if (init?.method === "PATCH") return { activity_id: "act-1", document_kind: "invoice", status: "cobrado", settled_on: "2026-10-18", payment_method: "otro", changed: true };
      return wire;
    });
    const loaded = await client.load("2026-10");
    expect(calls[0]).toEqual({ path: "/business/month-close?month=2026-10", method: "GET", body: undefined });
    expect(loaded.closed).toBe(false);
    expect(loaded.figures).toEqual([]);
    expect(loaded.documents.map((item) => item.id)).toEqual(["act-1"]);
    expect(loaded.blockers).toEqual([{ kind: "missing_rnc", id: "act-1:missing_rnc", documentId: "act-1" }]);
    await client.markCobrado("act-1", undefined, { settled_on: "2026-10-18", payment_method: "otro" });
    expect(JSON.parse(calls[1].body ?? "{}")).toEqual({ status: "cobrado", settled_on: "2026-10-18", payment_method: "otro" });
    expect(calls[1].method).toBe("PATCH");
    await expect(client.closeMonth("2026-10")).rejects.toMatchObject({ code: "unavailable" });
    expect(calls).toHaveLength(2);
  });

  test("a mark on a document the bank match settled is the matched error, for cobrado, pagado and Deshacer", async () => {
    const client = createHttpMonthCloseClient(async () => {
      throw Object.assign(new Error("Business document matched"), { status: 409, code: "business_document_matched" });
    });
    const settlement = { settled_on: "2026-10-18", payment_method: "otro" };
    await expect(client.markCobrado("act-1", undefined, settlement)).rejects.toMatchObject({ code: "matched" });
    await expect(client.markPagado("act-2", undefined, settlement)).rejects.toMatchObject({ code: "matched" });
    await expect(client.markPendiente("act-2")).rejects.toMatchObject({ code: "matched" });
  });

  test("an empty document list stays empty, and a failed load is an error", async () => {
    const snapshot = readMonthCloseWire({ ...wire, reasons: [], missing_rnc: [] });
    expect(snapshot.documents).toEqual([]);
    expect(snapshot.figures).toEqual([]);
    const client = createHttpMonthCloseClient(async () => {
      throw Object.assign(new Error("down"), { code: "business_month_close_unavailable" });
    });
    await expect(client.load("2026-10")).rejects.toMatchObject({ code: "unavailable" });
  });
});

const mappedWire = {
  month: "2026-10",
  from: "2026-10-01",
  to: "2026-10-31",
  closed: true,
  reasons: [],
  currencies: [
    {
      currency: "USD",
      income_before_itbis_minor: 100,
      income_before_itbis: "1.00",
      expense_before_itbis_minor: 100,
      expense_before_itbis: "1.00",
      net_result_minor: 100,
      net_result: "1.00",
      itbis_charged_minor: 100,
      itbis_charged: "1.00",
      itbis_owed_minor: 100,
      itbis_owed: "1.00",
    },
    {
      currency: "DOP",
      income_before_itbis_minor: 400000,
      income_before_itbis: "4000.00",
      expense_before_itbis_minor: 150000,
      expense_before_itbis: "1500.00",
      net_result_minor: 250000,
      net_result: "2500.00",
      itbis_charged_minor: 72000,
      itbis_charged: "720.00",
      itbis_owed_minor: 18000,
      itbis_owed: "180.00",
      by_status: {
        invoices: {
          pendiente: { count: 1, before_itbis_minor: 100000 },
          cobrado: { count: 2, before_itbis_minor: 200000 },
        },
        receipts: {
          pendiente: { count: 0, before_itbis_minor: 0 },
          pagado: { count: 1, before_itbis_minor: 100000 },
        },
      },
    },
  ],
  missing_rnc: [],
  missing_ncf: [],
  cuentas_por_cobrar: [{
    activity_id: "act-cobro",
    document_kind: "invoice",
    currency: "DOP",
    occurred_on: "2026-10-04",
    total_minor: 118000,
    before_itbis_minor: 100000,
    itbis_minor: 18000,
    status: "pendiente",
  }],
  cuentas_por_pagar: [],
};

describe("live figure mapping", () => {
  const dopBlock = () => readMonthCloseWire(mappedWire).figures.find((figures) => figures.currency === "DOP");

  test("M3 net reads net_result, not income", () => {
    expect(dopBlock()?.net_before_itbis).toBe("2500.00");
    expect(dopBlock()?.income_before_itbis).toBe("4000.00");
  });

  test("M4 the ITBIS card reads itbis_owed, not itbis_charged", () => {
    expect(dopBlock()?.itbis_owed).toBe("180.00");
  });

  test("M5 every currency keeps its own block, in the server's order", () => {
    expect(readMonthCloseWire(mappedWire).figures).toEqual([
      { currency: "USD", income_before_itbis: "1.00", expense_before_itbis: "1.00", net_before_itbis: "1.00", itbis_owed: "1.00", itbis_cobrado: null, net_result_final: null, pending_count: null },
      { currency: "DOP", income_before_itbis: "4000.00", expense_before_itbis: "1500.00", net_before_itbis: "2500.00", itbis_owed: "180.00", itbis_cobrado: null, net_result_final: null, pending_count: 1 },
    ]);
  });

  test("M6 minor units stay in cents", () => {
    expect(readMonthCloseWire(mappedWire).documents[0]?.amount).toBe("1180.00");
  });

  test("M7 a document keeps its itbis_minor", () => {
    expect(readMonthCloseWire(mappedWire).documents[0]?.itbis).toBe("180.00");
  });

  test("each currency's figures come from its own documents and are never added together", () => {
    const dop = document({ id: "dop", kind: "invoice", amount: "118.00", itbis: "18.00", status: "cobrado" });
    const usd = { ...document({ id: "usd", kind: "invoice", amount: "50.00", itbis: "5.00", status: "cobrado" }), currency: "USD" };
    const eur = { ...document({ id: "eur", kind: "receipt", amount: "20.00", itbis: "2.00", status: "pagado" }), currency: "EUR" };
    expect(monthCloseFiguresFrom([dop, usd, eur])).toEqual([
      { currency: "DOP", income_before_itbis: "100.00", expense_before_itbis: "0.00", net_before_itbis: "100.00", itbis_owed: "18.00", itbis_cobrado: "18.00", net_result_final: true, pending_count: 0 },
      { currency: "EUR", income_before_itbis: "0.00", expense_before_itbis: "18.00", net_before_itbis: "-18.00", itbis_owed: "-2.00", itbis_cobrado: "0.00", net_result_final: true, pending_count: 0 },
      { currency: "USD", income_before_itbis: "45.00", expense_before_itbis: "0.00", net_before_itbis: "45.00", itbis_owed: "5.00", itbis_cobrado: "5.00", net_result_final: true, pending_count: 0 },
    ]);
  });

  test("a wire line keeps its own currency", () => {
    const line = {
      activity_id: "act-usd",
      document_kind: "receipt",
      currency: "USD",
      occurred_on: "2026-10-05",
      total_minor: 5000,
      before_itbis_minor: 4500,
      itbis_minor: 500,
      status: "pendiente",
    };
    const snapshot = readMonthCloseWire({
      ...mappedWire,
      currencies: [
        { currency: "DOP", income_before_itbis_minor: 100000, expense_before_itbis_minor: 0, net_result_minor: 100000, itbis_owed_minor: 1800 },
      ],
      cuentas_por_cobrar: [],
      cuentas_por_pagar: [line],
    });
    expect(snapshot.figures.map((figures) => figures.currency)).toEqual(["DOP"]);
    expect(snapshot.documents).toEqual([
      expect.objectContaining({ id: "act-usd", currency: "USD", amount: "50.00", itbis: "5.00" }),
    ]);
    expect(readMonthCloseWire(mappedWire).documents[0]?.currency).toBe("DOP");
  });
});

describe("open items", () => {
  const item = (activityId: string, kind: "invoice" | "receipt", currency: string, occurredOn: string, totalMinor: number) => ({
    activity_id: activityId,
    document_kind: kind,
    currency,
    occurred_on: occurredOn,
    total_minor: totalMinor,
    total: "ignored",
    before_itbis_minor: totalMinor,
    itbis_minor: null,
    counterparty: "Cliente de práctica",
    status: "pendiente",
  });

  test("the HTTP client reads GET /business/open-items with no query, through the month's transport", async () => {
    const calls: { path: string; method?: string }[] = [];
    const client = createHttpMonthCloseClient(async (path, init) => {
      calls.push({ path, method: init?.method });
      return {
        cuentas_por_cobrar: { count: 2, totals: [{ currency: "DOP", total_minor: 5900, total: "59.00" }, { currency: "USD", total_minor: 1050, total: "10.50" }], items: [item("act-1", "invoice", "DOP", "2026-09-12", 5900), item("act-2", "invoice", "USD", "2026-10-02", 1050)] },
        cuentas_por_pagar: { count: 0, totals: [], items: [] },
      };
    });
    const open = await client.openItems("grant-1");
    expect(calls).toEqual([{ path: "/business/open-items", method: "GET" }]);
    expect(openItemsRequest()).toEqual({ method: "GET", path: "/business/open-items" });
    expect(open.cuentas_por_cobrar.count).toBe(2);
    expect(open.cuentas_por_cobrar.totals).toEqual([{ currency: "DOP", total: "59.00" }, { currency: "USD", total: "10.50" }]);
    expect(open.cuentas_por_cobrar.items[0]).toEqual(expect.objectContaining({ id: "act-1", kind: "invoice", occurred_on: "2026-09-12", amount: "59.00", counterparty: "Cliente de práctica", status: "pendiente" }));
    expect(open.cuentas_por_pagar).toEqual({ count: 0, totals: [], overdue: null, items: [] });
  });

  test("the reader keeps the due day and fiscal facts the server sends, so live rows show lateness and fiscal marks", () => {
    const line = { ...item("act-9", "invoice", "DOP", "2026-09-12", 5900), due_on: "2026-09-20", rnc: "101-23456-7", ncf: "B0100000042", ecf: null, sin_comprobante: false };
    const open = readOpenItemsWire({ cuentas_por_cobrar: { count: 1, totals: [], items: [line] }, cuentas_por_pagar: { count: 0, totals: [], items: [] } });
    expect(open.cuentas_por_cobrar.items[0]).toEqual(expect.objectContaining({ due_on: "2026-09-20", rnc: "101-23456-7", ncf: "B0100000042", ecf: null, sin_comprobante: false, fiscal_known: true }));
    const older = readOpenItemsWire({ cuentas_por_cobrar: { count: 1, totals: [], items: [item("act-8", "invoice", "DOP", "2026-09-12", 5900)] }, cuentas_por_pagar: { count: 0, totals: [], items: [] } });
    expect(older.cuentas_por_cobrar.items[0]).toEqual(expect.objectContaining({ due_on: null, rnc: null, fiscal_known: false }));
  });

  test("a refused open-items read is the same month close error", async () => {
    const client = createHttpMonthCloseClient(async () => {
      throw Object.assign(new Error("grant revoked"), { code: "business_grant_not_live" });
    });
    await expect(client.openItems()).rejects.toMatchObject({ name: "MonthCloseError", code: "unavailable" });
  });

  test("the reader refuses a settled item, an item in the wrong list, a fractional minor, or a count below its items", () => {
    const body = (cobrar: unknown) => ({ cuentas_por_cobrar: cobrar, cuentas_por_pagar: { count: 0, totals: [], items: [] } });
    expect(() => readOpenItemsWire(body({ count: 1, totals: [], items: [{ ...item("a", "invoice", "DOP", "2026-09-01", 100), status: "cobrado" }] }))).toThrow(MonthCloseError);
    expect(() => readOpenItemsWire(body({ count: 1, totals: [], items: [item("a", "receipt", "DOP", "2026-09-01", 100)] }))).toThrow(MonthCloseError);
    expect(() => readOpenItemsWire(body({ count: 1, totals: [{ currency: "DOP", total_minor: 1.5 }], items: [] }))).toThrow(MonthCloseError);
    expect(() => readOpenItemsWire(body({ count: 0, totals: [], items: [item("a", "invoice", "DOP", "2026-09-01", 100)] }))).toThrow(MonthCloseError);
    expect(() => readOpenItemsWire({})).toThrow(MonthCloseError);
  });

  test("the mock lists every month's pending documents oldest first, and a mark removes it", async () => {
    const client = createMockMonthCloseClient({ now });
    const before = await client.openItems();
    const receivable = before.cuentas_por_cobrar.items.map((document) => document.id);
    expect(receivable).toEqual(["inv-luna", "inv-farmacia", "inv-taller"]);
    expect(before.cuentas_por_pagar.items.map((document) => document.id)).toEqual(["rcpt-rosa", "rcpt-edenorte", "rcpt-transporte"]);
    expect(before.cuentas_por_cobrar.totals).toEqual([{ currency: "DOP", total: "33540.00" }]);
    expect((await client.load("2026-10")).documents.some((document) => document.id === "inv-luna")).toBe(false);
    await client.markCobrado("inv-luna");
    const after = await client.openItems();
    expect(after.cuentas_por_cobrar.items.map((document) => document.id)).toEqual(["inv-farmacia", "inv-taller"]);
    expect(after.cuentas_por_cobrar.count).toBe(2);
    expect(after.cuentas_por_cobrar.totals).toEqual([{ currency: "DOP", total: "27640.00" }]);
    expect((await client.openItems("other-grant")).cuentas_por_cobrar.count).toBe(3);
  });

  test("totals are one per currency and never added together; the header is the Business currency, never a guessed one", () => {
    const pending = (id: string, currency: string, amount: string): MonthCloseDocument => ({ ...document({ id, kind: "invoice", amount, itbis: null, status: "pendiente" }), currency });
    const list = openItemsFrom([pending("usd", "USD", "50.00"), pending("dop-1", "DOP", "100.00"), pending("dop-2", "DOP", "18.50"), pending("eur", "EUR", "20.00")], "2026-10-18").cuentas_por_cobrar;
    expect(list.totals).toEqual([{ currency: "DOP", total: "118.50" }, { currency: "EUR", total: "20.00" }, { currency: "USD", total: "50.00" }]);
    expect(openItemsHeaderCurrency(list, "DOP")).toBe("DOP");
    expect(openItemsHeaderCurrency(list, "USD")).toBe("USD");
    expect(openItemsHeaderCurrency(list)).toBe(null);
    expect(openItemsHeaderCurrency(list, "JPY")).toBe(null);
    const serverOrder = { ...list, totals: [{ currency: "USD", total: "50.00" }, { currency: "EUR", total: "20.00" }, { currency: "DOP", total: "118.50" }] };
    expect(openItemsTotalsInOrder(serverOrder, "DOP").map((total) => total.currency)).toEqual(["DOP", "USD", "EUR"]);
    expect(openItemsTotalsInOrder(serverOrder).map((total) => total.currency)).toEqual(["USD", "EUR", "DOP"]);
    const usdOnly = openItemsFrom([pending("usd", "USD", "50.00")], "2026-10-18").cuentas_por_cobrar;
    expect(openItemsHeaderCurrency(usdOnly)).toBe("USD");
    expect(openItemsHeaderCurrency(usdOnly, "DOP")).toBe("USD");
    expect(openItemsHeaderCurrency(openItemsFrom([], "2026-10-18").cuentas_por_cobrar)).toBe(null);
  });

  test("the mock caps the list at the oldest 100 and counts the rest", () => {
    const many = Array.from({ length: OPEN_ITEMS_CAP + 7 }, (_, index) => document({ id: `inv-${String(index).padStart(3, "0")}`, kind: "invoice", amount: "1.00", itbis: null, status: "pendiente", occurred_on: `2026-${String((index % 9) + 1).padStart(2, "0")}-01` }));
    const list = openItemsFrom(many, "2026-10-18").cuentas_por_cobrar;
    expect(list.count).toBe(107);
    expect(list.items.length).toBe(100);
    expect(list.items[0]?.occurred_on).toBe("2026-01-01");
    expect(list.totals).toEqual([{ currency: "DOP", total: "107.00" }]);
  });
});

describe("Pendiente hoy order and the sample books' overdue", () => {
  const today = "2026-10-18";
  const pending = (id: string, due_on: string | null, amount = "1.00", currency = "DOP", occurred_on = "2026-10-01"): MonthCloseDocument => ({ ...document({ id, kind: "invoice", amount, itbis: null, status: "pendiente", due_on, occurred_on }), currency });

  test("overdue rows lead, oldest first, then the nearest due, then rows with no due day by issue day", () => {
    const rows = [pending("soon", "2026-10-20"), pending("none-late", null, "1.00", "DOP", "2026-10-09"), pending("late-2", "2026-10-16"), pending("today", today), pending("late-30", "2026-09-18"), pending("none-early", null, "1.00", "DOP", "2026-09-02"), pending("far", "2026-11-30")];
    expect(openItemsInDueOrder(rows).map((row) => row.id)).toEqual(["late-30", "late-2", "today", "soon", "far", "none-early", "none-late"]);
  });

  test("the sample books answer overdue as the server does: exact, per currency, over every item, due today is not late", () => {
    const items = [pending("a", "2026-10-01", "0.10"), pending("b", "2026-10-02", "0.20"), pending("c", "2026-10-17", "12299.70"), pending("usd", "2026-09-30", "50.00", "USD"), pending("due-today", today, "999.00"), pending("none", null, "5.00")];
    const list = openItemsFrom(items, today).cuentas_por_cobrar;
    expect(list.overdue).toEqual({ count: 4, totals: [{ currency: "DOP", total: "12300.00" }, { currency: "USD", total: "50.00" }] });
    expect(overdueTotalsInOrder(list, "USD").map((total) => total.currency)).toEqual(["USD", "DOP"]);
    expect(openItemsFrom([pending("due-today", today)], today).cuentas_por_cobrar.overdue).toEqual({ count: 0, totals: [] });
  });

  test("Deshacer is a PATCH back to pendiente with neither a day nor a method, and the mock returns the row to the open items", async () => {
    expect(monthCloseReopenRequest("act-1")).toEqual({ method: "PATCH", path: "/business/month-close/documents/act-1", body: { status: "pendiente" } });
    const bodies: unknown[] = [];
    const http = createHttpMonthCloseClient(async (_path, init) => {
      bodies.push(JSON.parse(String(init?.body)));
      return { activity_id: "act-1", document_kind: "invoice", status: "pendiente", settled_on: null, payment_method: null, changed: true };
    });
    await http.markPendiente("act-1");
    expect(bodies).toEqual([{ status: "pendiente" }]);
    const refused = createHttpMonthCloseClient(async () => ({ activity_id: "act-1", status: "cobrado" }));
    await expect(refused.markPendiente("act-1")).rejects.toMatchObject({ code: "unavailable" });
    const mock = createMockMonthCloseClient({ now: new Date(2026, 9, 18) });
    await mock.markCobrado("inv-luna");
    expect((await mock.openItems()).cuentas_por_cobrar.items.some((item) => item.id === "inv-luna")).toBe(false);
    await mock.markPendiente("inv-luna");
    expect((await mock.openItems()).cuentas_por_cobrar.items.some((item) => item.id === "inv-luna")).toBe(true);
  });
});


function closePacket(extra: Record<string, unknown> = {}) {
  return {
    month: "2026-10",
    from: "2026-10-01",
    to: "2026-10-31",
    closed: false,
    reasons: [] as unknown[],
    currencies: [],
    missing_rnc: [],
    missing_ncf: [],
    cuentas_por_cobrar: [],
    cuentas_por_pagar: [],
    ...extra,
  };
}

describe("unreviewed drafts in the Bandeja", () => {
  test("a month with five unreviewed drafts loads, keeps document blockers, and carries the count", () => {
    const snapshot = readMonthCloseWire(closePacket({
      closed: false,
      reasons: [
        { code: "missing_rnc", activity_id: "act-1", document_kind: "invoice" },
        { code: "movimientos_sin_revisar", count: 5 },
      ],
      unreviewed_movements_count: 5,
      missing_rnc: [{ activity_id: "act-1", document_kind: "invoice", currency: "DOP", occurred_on: "2026-10-02", total_minor: 640000, before_itbis_minor: 640000, itbis_minor: null, status: "pendiente" }],
    }));
    expect(snapshot.closed).toBe(false);
    expect(snapshot.unreviewed_movements).toBe(5);
    expect(snapshot.blockers).toEqual([{ kind: "missing_rnc", id: "act-1:missing_rnc", documentId: "act-1" }]);
    expect(canCloseMonth(snapshot)).toEqual({ ok: false, reason: "blockers" });
  });

  test("an older packet with neither the reason nor the count is zero unreviewed", () => {
    expect(readMonthCloseWire(closePacket()).unreviewed_movements).toBe(0);
  });

  test("the count on the packet is used when the reason is absent, and a mismatch or a bad count is unavailable", () => {
    expect(readMonthCloseWire(closePacket({ unreviewed_movements_count: 2 })).unreviewed_movements).toBe(2);
    expect(readMonthCloseWire(closePacket({ reasons: [{ code: "movimientos_sin_revisar", count: 3 }] })).unreviewed_movements).toBe(3);
    expect(() => readMonthCloseWire(closePacket({
      reasons: [{ code: "movimientos_sin_revisar", count: 5 }],
      unreviewed_movements_count: 4,
    }))).toThrow(MonthCloseError);
    expect(() => readMonthCloseWire(closePacket({ reasons: [{ code: "movimientos_sin_revisar", count: 1.5 }] }))).toThrow(MonthCloseError);
    expect(() => readMonthCloseWire(closePacket({ reasons: [{ code: "not_a_reason", activity_id: "act-9" }] }))).toThrow(MonthCloseError);
    try {
      readMonthCloseWire(closePacket({ reasons: [{ code: "not_a_reason", activity_id: "act-9" }] }));
    } catch (error) {
      expect(error).toBeInstanceOf(MonthCloseError);
      expect((error as MonthCloseError).code).toBe("unavailable");
    }
  });

  test("a closed flag does not win over unreviewed drafts", () => {
    const snapshot = readMonthCloseWire(closePacket({
      closed: true,
      reasons: [{ code: "movimientos_sin_revisar", count: 1 }],
      unreviewed_movements_count: 1,
    }));
    expect(canCloseMonth({ ...snapshot, closed_at: "2026-10-18T15:00:00.000Z" })).toEqual({ ok: false, reason: "blockers" });
  });
});

test("a new local business has no seeded month figures or outstanding invoices", async () => {
  const client = createMockMonthCloseClient({ empty: true, now: new Date("2026-10-25T12:00:00Z") });
  const month = await client.load("2026-10", "local-business-empty");
  expect(month.documents).toEqual([]);
  expect(month.figures).toEqual([]);
  const open = await client.openItems("local-business-empty");
  expect(open.cuentas_por_cobrar.items).toEqual([]);
  expect(open.cuentas_por_pagar.items).toEqual([]);
});
