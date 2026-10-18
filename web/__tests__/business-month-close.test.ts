import { describe, expect, test } from "bun:test";
import { periodRange } from "../components/business-app/business-format";
import {
  MonthCloseError,
  calendarMonthOf,
  closeGate,
  createMockMonthCloseClient,
  fiscalNumberPresent,
  monthCloseBlockers,
  monthCloseSampleDocuments,
  monthCloseSummary,
  readMonthCloseDocument,
  rncPresent,
  type MonthCloseDocument,
} from "../lib/business-month-close";

const now = new Date(2026, 9, 18);

function document(partial: Pick<MonthCloseDocument, "id" | "kind" | "amount" | "itbis" | "status"> & Partial<MonthCloseDocument>): MonthCloseDocument {
  return {
    counterparty: partial.id,
    occurred_on: "2026-10-01",
    rnc: "131-99988-8",
    ncf: "B0100000001",
    ecf: null,
    ...partial,
  };
}

describe("month close money", () => {
  test("net is income minus expenses before ITBIS, and ITBIS owed is the tax difference", () => {
    const summary = monthCloseSummary([
      document({ id: "invoice", kind: "invoice", amount: "118.00", itbis: "18.00", status: "cobrado" }),
      document({ id: "receipt", kind: "receipt", amount: "59.00", itbis: null, status: "pagado" }),
    ]);
    expect(summary).toEqual({ currency: "DOP", net_before_itbis: "41.00", itbis_owed: "18.00" });
  });

  test("a missing ITBIS counts as zero and is not invented from the total", () => {
    const summary = monthCloseSummary([
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
    expect(monthCloseSummary(current)).toEqual({ currency: "DOP", net_before_itbis: "48800.00", itbis_owed: "7902.00" });
    expect(monthCloseSummary(previous)).toEqual({ currency: "DOP", net_before_itbis: "14200.00", itbis_owed: "2556.00" });
  });
});

describe("month close blockers and the close gate", () => {
  test("pending items and a missing RNC or NCF block the month; an e-CF counts as the comprobante", () => {
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
      "pending:pending",
      "zeros:missing_rnc",
    ]);
  });

  test("the sample month lists pending rows and the documents missing an RNC or a comprobante", () => {
    const current = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-10"));
    const ids = monthCloseBlockers(current).map((blocker) => blocker.id);
    expect(ids).toContain("inv-taller:pending");
    expect(ids).toContain("inv-farmacia:missing_rnc");
    expect(ids).toContain("inv-caribe:missing_ncf");
    expect(ids).toContain("rcpt-transporte:pending");
    expect(ids).toContain("rcpt-transporte:missing_rnc");
    expect(ids).toContain("rcpt-transporte:missing_ncf");
    expect(ids).not.toContain("inv-taller:missing_ncf");
  });

  test("close stays shut until the window is one calendar month with no blockers", () => {
    const open = monthCloseSampleDocuments(now).filter((item) => item.occurred_on.startsWith("2026-10"));
    expect(closeGate({ month: "2026-10", closed_at: null, documents: open })).toEqual({ ok: false, reason: "blockers" });
    expect(closeGate({ month: null, closed_at: null, documents: [] })).toEqual({ ok: false, reason: "not_calendar_month" });
    expect(closeGate({ month: "2026-09", closed_at: "2026-10-01T12:00:00.000Z", documents: [] })).toEqual({ ok: false, reason: "closed" });
    expect(calendarMonthOf("2026-10-01", null, "2026-10-18")).toBe("2026-10");
    expect(calendarMonthOf("2026-09-01", "2026-09-30", "2026-10-18")).toBe("2026-09");
    expect(calendarMonthOf("2026-09-19", null, "2026-10-18")).toBeNull();
    expect(calendarMonthOf("2000-01-01", null, "2026-10-18")).toBeNull();
    expect(calendarMonthOf("2026-08-01", "2026-08-15", "2026-10-18")).toBeNull();
    expect(closeGate({ month: "2026-09", closed_at: null, documents: [] })).toEqual({ ok: true, month: "2026-09" });
  });

  test("a paid invoice and an early month day still parse, and a mismatched status does not", () => {
    expect(readMonthCloseDocument({
      id: "inv-1",
      kind: "invoice",
      counterparty: "Colmado Don Luis",
      occurred_on: "2026-10-01",
      amount: "10",
      itbis: null,
      rnc: "131-99988-8",
      ncf: "B0100000001",
      ecf: null,
      status: "pendiente",
      currency: "DOP",
    }).amount).toBe("10.00");
    expect(() => readMonthCloseDocument({
      id: "inv-1",
      kind: "invoice",
      counterparty: "Colmado Don Luis",
      occurred_on: "2026-10-01",
      amount: "10.00",
      itbis: null,
      rnc: null,
      ncf: null,
      ecf: null,
      status: "pagado",
    })).toThrow(MonthCloseError);
  });
});

describe("month close mock client", () => {
  test("marks collection and payment, then closes only after the blockers are gone", async () => {
    const client = createMockMonthCloseClient({ now });
    const lastMonth = periodRange("last_month", now);
    let snapshot = await client.load(lastMonth);
    expect(snapshot.month).toBe("2026-09");
    expect(closeGate(snapshot).ok).toBe(false);
    await expect(client.markPagado("inv-luna")).rejects.toMatchObject({ code: "invalid_status" });
    await client.markCobrado("inv-luna");
    await client.markPagado("rcpt-rosa");
    snapshot = await client.load(lastMonth);
    expect(closeGate(snapshot)).toEqual({ ok: true, month: "2026-09" });
    const closed = await client.closeMonth("2026-09");
    expect(closed.closed_at).toBeTruthy();
    expect(closed.documents.every((item) => item.status !== "pendiente")).toBe(true);
    await expect(client.markCobrado("inv-luna")).rejects.toMatchObject({ code: "closed" });
    await expect(client.closeMonth("2026-10")).rejects.toMatchObject({ code: "blockers" });
  });

  test("a failed mark leaves the stored status untouched", async () => {
    const client = createMockMonthCloseClient({ now, failIds: ["inv-taller"] });
    await expect(client.markCobrado("inv-taller")).rejects.toMatchObject({ code: "unavailable" });
    const snapshot = await client.load(periodRange("this_month", now));
    expect(snapshot.documents.find((item) => item.id === "inv-taller")?.status).toBe("pendiente");
  });
});
