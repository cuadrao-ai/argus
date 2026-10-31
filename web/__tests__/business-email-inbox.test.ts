import { afterEach, beforeEach, describe, expect, test } from "bun:test";
import { createFixtureBusinessDataSource } from "@/components/business-app/fixture-data";
import { inboxCount } from "@/components/business-app/inbox-count";
import { bandejaReviewNote, receptionRows } from "@/components/business-app/recepcion/reception-model";
import { getBusinessEmailInbox, setBusinessEmailSender } from "@/lib/business-api";

type Call = { url: string; method: string; body: unknown };

function respond(status: number, body: unknown): Call[] {
  const calls: Call[] = [];
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), method: init?.method ?? "GET", body: init?.body ? JSON.parse(String(init.body)) : null });
    return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  return calls;
}

const activity = { reading_count: 0, unread_count: 0, presentation: "none" as const, pending_review_count: 2, needs_attention_count: 0, ready_to_review_count: 2 };

describe("business email inbox client", () => {
  const originalFetch = globalThis.fetch;
  const originalMockAuth = process.env.NEXT_PUBLIC_MOCK_AUTH;
  beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; });
  afterEach(() => {
    globalThis.fetch = originalFetch;
    if (originalMockAuth === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH;
    else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMockAuth;
  });

  test("getBusinessEmailInbox calls /business/email/inbox and returns groups in API order", async () => {
    const groups = [
      { id: "bandeja", items: [{ id: "later" }] },
      { id: "remitentes_nuevos", items: [{ id: "first" }] },
    ];
    const calls = respond(200, { groups });
    const result = await getBusinessEmailInbox();
    expect(new URL(calls[0].url).pathname).toBe("/api/v1/business/email/inbox");
    expect(calls[0].method).toBe("GET");
    expect(result.map((group) => group.id)).toEqual(["bandeja", "remitentes_nuevos"]);
    expect(result[0].items[0].id).toBe("later");
    expect(result[1].items[0].id).toBe("first");
  });

  test("a missing groups list is no groups", async () => {
    respond(200, {});
    expect(await getBusinessEmailInbox()).toEqual([]);
  });

  test("setBusinessEmailSender posts the address and status once", async () => {
    const calls = respond(201, { id: "rule-1", kind: "address", value: "nuevo@proveedor.example", status: "authorized" });
    const saved = await setBusinessEmailSender({ kind: "address", value: "nuevo@proveedor.example", status: "authorized" });
    expect(calls).toHaveLength(1);
    expect(new URL(calls[0].url).pathname).toBe("/api/v1/business/email/senders");
    expect(calls[0].method).toBe("POST");
    expect(calls[0].body).toEqual({ kind: "address", value: "nuevo@proveedor.example", status: "authorized" });
    expect(saved.id).toBe("rule-1");
  });
});

describe("Bandeja badge and review note", () => {
  test("the badge adds remitentes nuevos for the owner and not for a grantee", () => {
    const emailInbox = [
      { id: "remitentes_nuevos", items: [{ id: "a" }, { id: "b" }] },
      { id: "bandeja", items: [{ id: "c" }] },
    ];
    expect(inboxCount({ receiptActivity: activity, emailInbox }, { role: "owner" })).toBe(4);
    expect(inboxCount({ receiptActivity: activity, emailInbox }, { role: "accountant" })).toBe(2);
    expect(inboxCount({ receiptActivity: activity, emailInbox: [{ id: "remitentes_nuevos", items: [] }] }, { role: "owner" })).toBe(2);
    expect(inboxCount({ receiptActivity: null, emailInbox }, { role: "owner" })).toBeNull();
  });

  test("a remitentes group with no items list adds nothing", () => {
    const base = { receiptActivity: activity };
    expect(inboxCount({ ...base, emailInbox: [{ id: "remitentes_nuevos", items: null }] }, { role: "owner" })).toBe(2);
    expect(inboxCount({ ...base, emailInbox: [{ id: "remitentes_nuevos" }] }, { role: "owner" })).toBe(2);
  });

  test("a bandeja item's review note is the API string, and null stays empty", async () => {
    const source = createFixtureBusinessDataSource({ chatAvailable: false });
    const receipt = { ...(await source.receipts("all"))[0], id: "rcpt-1", email_delivery_ids: ["mail-1"] };
    const email = { ...(await source.emailDeliveries())[0], id: "mail-1", standing: null, review_note: "Solo el correo" };
    const fromDelivery = receptionRows([receipt], [], [email]);
    const receiptRow = fromDelivery.find((row) => row.kind === "receipt");
    assertNote(receiptRow, "Solo el correo");
    expect(fromDelivery.some((row) => row.kind === "email")).toBe(false);
    const fromInbox = receptionRows([receipt], [], [{ ...email, review_note: null }], [{ id: "bandeja", items: [{ id: "mail-1", review_note: "Texto distinto 41" }] }]);
    assertNote(fromInbox.find((row) => row.kind === "receipt"), "Texto distinto 41");
    expect(fromInbox.some((row) => row.kind === "email")).toBe(false);
    const silent = receptionRows([receipt], [], [{ ...email, review_note: null }]);
    expect(bandejaReviewNote(silent.find((row) => row.kind === "receipt")!)).toBeNull();
  });
});

function assertNote(row: ReturnType<typeof receptionRows>[number] | undefined, note: string) {
  expect(row?.kind).toBe("receipt");
  if (row?.kind === "receipt") expect(row.reviewNote).toBe(note);
}
