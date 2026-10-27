import { afterEach, beforeEach, expect, test } from "bun:test";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { observeBrowserAuth } from "@/lib/browser-auth-generation";
import { downloadInvoiceArtifact, getInvoice, getCustomer, getInvoiceOperation, saveCustomer, invoiceSchema, prepareInvoice, saveInvoice, submitInvoice, type FiscalOperation } from "@/lib/business-invoices-api";
import { incompleteInvoice, invoiceId, invoiceScope, savedInvoice, savedCustomer } from "./fixtures/business-invoice-fixture";
const originalFetch = globalThis.fetch, originalGrant = getChosenGrant(), originalMock = process.env.NEXT_PUBLIC_MOCK_AUTH;
beforeEach(() => { process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; setChosenGrant(invoiceScope.grantId); });
afterEach(() => { globalThis.fetch = originalFetch; setChosenGrant(originalGrant); if (originalMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = originalMock; });
function operation(submission: FiscalOperation["state"]["submission"] = "prepared"): FiscalOperation {
  return { id: "60000000-0000-4000-8000-000000000006", invoice_id: invoiceId, invoice_revision_id: savedInvoice().revision_id, business_id: invoiceScope.businessId, case_id: "synthetic-invoice", kind: "E32", number: "E320000000001", payload_digest: "a".repeat(64), provider_id: null, state: { submission, processing: "unreported", legal: "unreported", xml: "available", pdf: "unreported", delivery: "not_requested", reconciliation: "not_needed", diagnostics: [], needs_review: false } };
}
test("incomplete save sends the exact submitted fields with one idempotency key and no customer POST", async () => {
  const calls: { path: string; options?: RequestInit }[] = [], data = incompleteInvoice(); data.customer_input.name = "Una entrada parcial";
  globalThis.fetch = async (path, options) => { calls.push({ path: String(path), options }); return Response.json(savedInvoice(data)); };
  const result = await saveInvoice(invoiceScope, null, "frozen-create-key", { data, expected_version: null });
  expect(calls).toHaveLength(1); expect(calls[0].path.endsWith("/business/invoices")).toBe(true);
  expect(new Headers(calls[0].options?.headers).get("Idempotency-Key")).toBe("frozen-create-key");
  expect(new Headers(calls[0].options?.headers).get("X-Business-Grant")).toBe(invoiceScope.grantId);
  expect(JSON.parse(String(calls[0].options?.body))).toEqual({ data, expected_version: null });
  expect(result.data.customer_input.name).toBe(data.customer_input.name); expect(result.data.customer_id).toBeNull(); expect(calls[0].options?.credentials).toBe("omit");
});
test("server money stays decimal text and payment/delivery remain explicitly unknown and unsent", () => {
  const record = { ...savedInvoice(), amounts: { subtotal: "9007199254740993.01", discount: "0.00", tax: "0.00", total: "9007199254740993.01" } };
  expect(invoiceSchema.parse(record).amounts?.total).toBe("9007199254740993.01");
  expect(invoiceSchema.parse(record).outstanding_amount).toBeNull();
  expect(invoiceSchema.safeParse({ ...record, paid_amount: "0.00" }).success).toBe(false);
  expect(invoiceSchema.safeParse({ ...record, delivery_state: "sent" }).success).toBe(false);
});
test("a switched grant aborts the request and never admits a late invoice response", async () => {
  let signal: AbortSignal | null | undefined;
  globalThis.fetch = async (_, options) => { signal = options?.signal; setChosenGrant(null); setChosenGrant(invoiceScope.grantId); return Response.json(savedInvoice()); };
  await expect(getInvoice(invoiceScope, invoiceId)).rejects.toThrow(); expect(signal?.aborted).toBe(true);
});
test("another Business response or mismatched operation revision is rejected", async () => {
  globalThis.fetch = async () => Response.json({ ...savedInvoice(), business_id: "70000000-0000-4000-8000-000000000007" });
  await expect(getInvoice(invoiceScope, invoiceId)).rejects.toThrow("scope changed");
  globalThis.fetch = async () => Response.json({ ...savedInvoice(), operation: { ...operation(), invoice_revision_id: "70000000-0000-4000-8000-000000000007" } });
  await expect(getInvoice(invoiceScope, invoiceId)).rejects.toThrow("scope changed");
});
test("an authenticated account change during body reading rejects the response", async () => {
  observeBrowserAuth("invoice-old-account");
  globalThis.fetch = async () => { const response = Response.json(savedInvoice()); response.json = async () => { observeBrowserAuth("invoice-next-account"); return savedInvoice(); }; return response; };
  await expect(getInvoice(invoiceScope, invoiceId)).rejects.toThrow("Browser session changed");
});
test("prepare reuses the saved invoice and reviewed version without a fixture operation or submit", async () => {
  const calls: { path: string; body: unknown }[] = [];
  globalThis.fetch = async (path, options) => { calls.push({ path: String(path), body: JSON.parse(String(options?.body)) }); return Response.json({ ...savedInvoice(), operation: operation() }); };
  const result = await prepareInvoice(invoiceScope, invoiceId, 1);
  expect(calls).toEqual([{ path: expect.stringContaining(`/business/invoices/${invoiceId}/prepare`), body: { expected_version: 1 } }]); expect(result.operation?.state.submission).toBe("prepared"); expect(result.operation?.state.legal).toBe("unreported");
});
test("an uncertain submit reconciles the same operation before considering another POST", async () => {
  const calls: string[] = [], current = operation("unknown");
  globalThis.fetch = async (path, options) => { calls.push(`${options?.method ?? "GET"} ${String(path)}`); return Response.json(String(path).includes("/business/invoices/") ? { ...savedInvoice(), operation: current } : current); };
  const result = await submitInvoice(invoiceScope, invoiceId, current.id, current.payload_digest);
  expect(calls).toHaveLength(2); expect(calls.every(path => path.startsWith("GET"))).toBe(true); expect(result.operation?.state.submission).toBe("unknown");
});
test("a prepared operation submits only its immutable server digest and identity", async () => {
  const prepared = operation(), calls: { path: string; body?: unknown }[] = [];
  globalThis.fetch = async (path, options) => { calls.push({ path: String(path), body: options?.body ? JSON.parse(String(options.body)) : undefined }); return Response.json(String(path).includes("/business/invoices/") ? { ...savedInvoice(), operation: prepared } : String(path).endsWith("/submit") ? operation("identified") : prepared); };
  const result = await submitInvoice(invoiceScope, invoiceId, prepared.id, prepared.payload_digest);
  expect(calls[2]).toEqual({ path: expect.stringContaining(`/fiscal-operations/${prepared.id}/submit`), body: { payload_digest: prepared.payload_digest } }); expect(result.operation?.state.submission).toBe("identified"); expect(result.operation?.state.legal).toBe("unreported");
});
test("original XML is authenticated and unavailable PDF never requests bytes", async () => {
  const invoice = { ...savedInvoice(), operation: operation() }; let calls = 0;
  globalThis.fetch = async (_, options) => { calls++; expect(new Headers(options?.headers).get("X-Business-Grant")).toBe(invoiceScope.grantId); return new Response("<synthetic/>", { headers: { "Content-Type": "application/xml" } }); };
  expect(await (await downloadInvoiceArtifact(invoiceScope, invoice, "xml")).text()).toBe("<synthetic/>");
  await expect(downloadInvoiceArtifact(invoiceScope, invoice, "pdf")).rejects.toThrow("unavailable"); expect(calls).toBe(1);
});

test("targeted reads and writes reject a different record in the same Business", async () => {
  const wrong = "70000000-0000-4000-8000-000000000007";
  globalThis.fetch = async () => Response.json({ ...savedInvoice(), id: wrong });
  await expect(getInvoice(invoiceScope, invoiceId)).rejects.toThrow("scope changed");
  await expect(saveInvoice(invoiceScope, invoiceId, "same-target", { data: incompleteInvoice(), expected_version: 1 })).rejects.toThrow("scope changed");
  await expect(prepareInvoice(invoiceScope, invoiceId, 1)).rejects.toThrow("scope changed");
  const customer = savedCustomer(); globalThis.fetch = async () => Response.json({ ...customer, id: wrong });
  await expect(getCustomer(invoiceScope, customer.id)).rejects.toThrow("scope changed");
  await expect(saveCustomer(invoiceScope, customer.id, "same-customer", { data: customer.data, archived: false, expected_version: 1 })).rejects.toThrow("scope changed");
});
test("fiscal reads and submit reject a changed operation identity or digest", async () => {
  const prepared = operation(), invoice = { ...savedInvoice(), operation: prepared };
  globalThis.fetch = async () => Response.json({ ...prepared, id: "70000000-0000-4000-8000-000000000007" });
  await expect(getInvoiceOperation(invoiceScope, invoice)).rejects.toThrow("scope changed");
  globalThis.fetch = async (path) => Response.json(String(path).includes("/business/invoices/") ? invoice : { ...prepared, payload_digest: "b".repeat(64) });
  await expect(submitInvoice(invoiceScope, invoiceId, prepared.id, prepared.payload_digest)).rejects.toThrow("scope changed");
});

test("artifact bytes are discarded when the selected authority changes during reading", async () => {
  const invoice = { ...savedInvoice(), operation: operation() };
  globalThis.fetch = async () => {
    const response = new Response("<synthetic/>", { headers: { "Content-Type": "application/xml" } });
    response.blob = async () => { setChosenGrant(null); setChosenGrant(invoiceScope.grantId); return new Blob(["<synthetic/>"]); };
    return response;
  };
  await expect(downloadInvoiceArtifact(invoiceScope, invoice, "xml")).rejects.toThrow("scope changed");
});
