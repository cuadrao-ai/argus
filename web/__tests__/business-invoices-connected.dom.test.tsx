import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { FiscalOperation, InvoiceDraft, SavedInvoice } from "@/lib/business-invoices-api";
import { invoiceId, invoiceScope, incompleteInvoice, savedInvoice, savedCustomer } from "./fixtures/business-invoice-fixture";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { removeSessionStored } from "@/lib/browser-storage";

const realFlags = { ...await import("@/lib/private-alpha-flags") };
mock.module("@/lib/private-alpha-flags", () => ({ ...realFlags, businessInvoicingEnabled: true }));

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz?view=invoicing" }); Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); });
afterAll(async () => { await GlobalRegistrator.unregister(); });
async function mount(options: { record?: SavedInvoice; loseCreate?: boolean; losePrepare?: boolean; holdCreate?: boolean; entry?: boolean; selectedGrant?: string | null; missingActor?: boolean; missingPermissions?: boolean } = {}) {
  const { act, StrictMode } = await import("react");
  const { createRoot } = await import("react-dom/client");
  const { I18nextProvider } = await import("react-i18next");
  const i18next = (await import("i18next")).default;
  const english = (await import("@/public/locales/en/common.json")).default;
  const { BusinessContext } = await import("@/components/business-app/BusinessWorkspace");
  const { createFixtureBusinessDataSource } = await import("@/components/business-app/fixture-data");
  const { periodRange } = await import("@/components/business-app/business-format");
  const { default: BusinessPanel } = await import("@/components/business-app/BusinessPanel");
  const { default: ConnectedInvoicingWorkspace } = await import("@/components/business-app/invoicing/ConnectedInvoicingWorkspace");
  const i18n = i18next.createInstance(); await i18n.init({ lng: "en", resources: { en: { translation: english } } });
  const previousFetch = globalThis.fetch, previousMock = process.env.NEXT_PUBLIC_MOCK_AUTH, previousGrant = getChosenGrant();
  process.env.NEXT_PUBLIC_MOCK_AUTH = "true"; setChosenGrant(options.selectedGrant === undefined ? invoiceScope.grantId : options.selectedGrant); removeSessionStored("cuadrao:invoice_commands:v1");
  let record = options.record ?? null, creates = 0, prepareEffects = 0, loseCreate = options.loseCreate, losePrepare = options.losePrepare;
  const calls: { path: string; method: string; body: unknown; key: string | null }[] = [];
  let releaseCreate: (() => void) | undefined; let heldSignal: AbortSignal | null | undefined;
  const createdCustomers: ReturnType<typeof savedCustomer>[] = [];
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input)), method = init?.method ?? "GET", body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path: url.pathname, method, body, key: new Headers(init?.headers).get("Idempotency-Key") });
    if (url.pathname.endsWith("/business/invoices") && method === "GET") return Response.json({ items: record ? [record] : [], total: record ? 1 : 0, page: 1, page_size: 25, stage_counts: { draft: record ? 1 : 0 }, summaries: [], query_version: "synthetic-version" });
    if (url.pathname.endsWith("/business/customers") && method === "GET") return Response.json({ items: createdCustomers, total: createdCustomers.length, page: 1, page_size: 25 });
    if (url.pathname.endsWith("/business/customers") && method === "POST") { const customer = { ...savedCustomer(), data: body.data }; createdCustomers.push(customer); return Response.json(customer); }
    if (url.pathname.endsWith("/business/invoices") && method === "POST") {
      if (!record) { record = savedInvoice(body.data); creates++; }
      if (options.holdCreate) { heldSignal = init?.signal; await new Promise<void>(resolve => { releaseCreate = resolve; }); }
      if (loseCreate) { loseCreate = false; throw new TypeError("synthetic response lost after commit"); }
      return Response.json(record);
    }
    if (url.pathname.endsWith(`/business/invoices/${invoiceId}`) && method === "PUT" && record) { record = { ...record, version: record.version + 1, data: body.data, amounts: body.data.tax_inclusion === "included" ? null : record.amounts }; return Response.json(record); }
    if (url.pathname.endsWith("/prepare") && record) {
      if (record.data.tax_inclusion === "included") return Response.json({ code: "invoice_not_ready", context: { field_errors: { tax_inclusion: "unsupported" } } }, { status: 422 });
      if (!record.operation) { record = { ...record, operation: preparedOperation() }; prepareEffects++; }
      if (losePrepare) { losePrepare = false; throw new TypeError("synthetic prepare response lost"); }
      return Response.json(record);
    }
    if (url.pathname.endsWith(`/business/invoices/${invoiceId}`) && record) return Response.json(record);
    return new Response(null, { status: 404 });
  };
  const source = createFixtureBusinessDataSource();
  const context: BusinessContextValue = { userId: options.missingActor ? null : invoiceScope.userId, source, records: { workspace: null, overview: null, inbox: [], notes: [], notesTruncated: false, emails: [], error: false }, spaces: [], chosen: { space_id: invoiceScope.businessId, grant_id: invoiceScope.grantId!, name: "Synthetic Business", role: "owner", capabilities: ["read", "prepare", "approve"], permissions: options.missingPermissions ? undefined : ["read", "prepare", "approve", "download"], access_seen: true }, chooseBusiness: () => undefined, markAccessSeen: async () => undefined, lostAccess: false, clearLostAccess: () => undefined, revision: 0, reload: () => undefined, refresh: async () => "updated", period: periodRange("all"), setPeriod: () => undefined, panel: { kind: "invoicing" }, openPanel: () => undefined, actions: { create: [], composer: [], starterEntries: [] }, bridge: null, attachedReceipt: null, clearAttachedReceipt: () => undefined, openExport: () => undefined, emailRefresh: { refresh: () => undefined, refreshing: false, stalled: false }, retrySources: () => undefined };
  const host = document.createElement("div"); document.body.append(host); let root = createRoot(host);
  const render = async () => { await act(async () => { root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={context}>{options.entry ? <BusinessPanel /> : <ConnectedInvoicingWorkspace scope={invoiceScope} business="Synthetic Business" capabilities={{ prepare: true, issue: false, download: true }} />}</BusinessContext.Provider></I18nextProvider></StrictMode>); }); };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent?.trim() === text && !node.closest("[hidden]")); assert.ok(found, `missing button ${text}`); return found; };
  const click = async (text: string) => { await act(async () => button(text).click()); };
  const fill = async (selector: string, value: string) => { const input = document.querySelector<HTMLInputElement>(selector); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); };
  const reopen = async () => { await act(async () => root.unmount()); root = createRoot(host); await render(); };
  return { calls, click, fill, button, act, reopen, release: () => releaseCreate?.(), signal: () => heldSignal, record: () => record, creates: () => creates, prepareEffects: () => prepareEffects, async close() { await act(async () => root.unmount()); host.remove(); globalThis.fetch = previousFetch; setChosenGrant(previousGrant); if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock; removeSessionStored("cuadrao:invoice_commands:v1"); } };
}
function preparedOperation(): FiscalOperation {
  return { id: "60000000-0000-4000-8000-000000000006", invoice_id: invoiceId, invoice_revision_id: savedInvoice().revision_id, business_id: invoiceScope.businessId, case_id: "synthetic-saved-revision", kind: "E32", number: "E320000000001", payload_digest: "a".repeat(64), provider_id: null, state: { submission: "prepared", processing: "unreported", legal: "unreported", xml: "unreported", pdf: "unreported", delivery: "not_requested", reconciliation: "not_needed", diagnostics: [], needs_review: false } };
}
test("real editor Save draft saves an empty draft with unknown fiscal fields and no customer creation", async () => {
  const page = await mount(); try {
    await page.click("Create invoice"); await page.click("Save draft");
    assert.equal(page.creates(), 1); assert.equal(page.record()?.data.payment_type, null); assert.deepEqual(page.record()?.data.items, []);
    assert.equal(page.calls.filter(call => call.method === "POST" && call.path.endsWith("/customers")).length, 0);
    assert.equal(page.calls.some(call => call.path.endsWith("/prepare") || call.path.endsWith("/submit")), false);
    assert.ok(document.body.textContent?.includes("Saved to this Business."));
  } finally { await page.close(); }
});
test("typing a name saves the invoice snapshot without implicitly posting a customer", async () => {
  const page = await mount(); try {
    await page.click("Create invoice"); await page.fill("#invoice-customer-search", "Unfinished customer"); await page.click("Save draft");
    assert.equal(page.record()?.data.customer_input.name, "Unfinished customer"); assert.equal(page.record()?.data.customer_id, null);
    assert.equal(page.calls.filter(call => call.method === "POST" && call.path.endsWith("/customers")).length, 0);
  } finally { await page.close(); }
});
test("lost create response reopens the same pending editor and retries one frozen command", async () => {
  const page = await mount({ loseCreate: true }); try {
    await page.click("Create invoice"); await page.fill("#invoice-customer-search", "Keep exact partial input"); await page.click("Save draft");
    assert.ok(document.body.textContent?.includes("Retry the same request")); await page.reopen(); await page.click("Retry the same request");
    const writes = page.calls.filter(call => call.method === "POST" && call.path.endsWith("/invoices")); assert.equal(writes.length, 2); assert.deepEqual(writes[1], writes[0]); assert.equal(page.creates(), 1);
  } finally { await page.close(); }
});
test("customer contact is posted only through explicit customer Save", async () => {
  const page = await mount(); try {
    await page.click("Customers"); await page.click("Add customer"); await page.fill("#customer-name", "Explicit contact"); await page.click("Save customer");
    assert.equal(page.calls.filter(call => call.method === "POST" && call.path.endsWith("/customers")).length, 1); assert.equal(page.creates(), 0);
  } finally { await page.close(); }
});
test("lost prepare response retries the same saved revision and never submits or reports issued", async () => {
  const data: InvoiceDraft = { ...incompleteInvoice(), customer_input: { ...incompleteInvoice().customer_input, name: "Saved customer input" }, payment_type: "cash", income_type: 1, tax_inclusion: "excluded", issued_on: "2026-10-27", due_on: "2026-10-27", items: [{ id: "item-one", description: "Service", quantity: "1", price: "100.01", discount: "0", tax: "0", classification: "services", tax_treatment: "exempt" }] };
  const page = await mount({ record: { ...savedInvoice(data), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } }, losePrepare: true }); try {
    await page.click(invoiceId); assert.ok(document.body.textContent?.includes("Preparing this invoice locks its details.")); await page.click("Prepare issuance"); await page.click("Retry the same request");
    const prepares = page.calls.filter(call => call.path.endsWith("/prepare")); assert.equal(prepares.length, 2); assert.deepEqual(prepares[1], prepares[0]); assert.equal(page.prepareEffects(), 1);
    assert.equal(page.calls.some(call => call.path.endsWith("/submit")), false); assert.ok(document.body.textContent?.includes("Prepared, not issued")); assert.equal(page.record()?.payment_state, "unknown"); assert.equal(page.record()?.delivery_state, "not_sent");
  } finally { await page.close(); }
});

test("saved decimal totals disappear after local price edits and included-tax save remains unknown", async () => {
  const data = { ...incompleteInvoice(), customer_input: { ...incompleteInvoice().customer_input, name: "Saved contact snapshot" }, issued_on: "2026-10-27", due_on: "2026-10-27", payment_type: "cash" as const, income_type: 1 as const, tax_inclusion: "excluded" as const, items: [{ id: "price-item", description: "Saved service", quantity: "1", price: "100.01", discount: "0", tax: "0", classification: "services" as const, tax_treatment: "exempt" as const }] };
  const page = await mount({ record: { ...savedInvoice(data), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } } });
  try {
    await page.click(invoiceId); await page.click("Edit draft"); await page.click("Next");
    const totals = () => document.querySelector('[data-testid="invoice-editor"] [data-testid="invoice-customer-document"] [class*="documentTotals"]')?.textContent;
    assert.ok(totals()?.includes("100.01")); await page.fill('#invoice-price-item-price', "200.020");
    await page.act(async () => { const input = document.querySelector<HTMLInputElement>("#invoice-price-item-price")!; input.focus(); input.blur(); });
    assert.ok(!totals()?.includes("100.01")); assert.ok(!totals()?.includes("200.02"));
    await page.click("Next");
    const taxLabel = [...document.querySelectorAll("span")].find(node => node.textContent === "Prices and tax"); assert.ok(taxLabel);
    const choice = taxLabel.parentElement?.querySelector("button"); assert.ok(choice); await page.act(async () => choice.click()); await page.click("Tax included"); await page.click("Save draft");
    assert.equal(page.record()?.data.items[0].price, "200.020"); assert.equal(page.record()?.data.tax_inclusion, "included"); assert.equal(page.record()?.amounts, null);
    await page.click("Prepare issuance"); assert.ok(document.body.textContent?.includes("Review the marked fields")); assert.equal(page.record()?.operation, null);
    await page.click("Edit draft"); assert.ok(document.body.textContent?.includes("not supported for issuing"));
    await page.reopen(); await page.click(invoiceId); await page.click("Edit draft"); await page.click("Next"); assert.equal(document.querySelector<HTMLInputElement>("#invoice-price-item-price")?.value, "200.020");
  } finally { await page.close(); }
});

test("the five fiscal choices remain blank until explicit selection and incomplete saves retain them", async () => {
  const page = await mount({ record: savedInvoice() });
  const choose = async (label: string, value: string) => { const span = [...document.querySelectorAll("span")].find(node => node.textContent === label); assert.ok(span, label); const button = span.parentElement?.querySelector("button"); assert.ok(button); await page.act(async () => button.click()); await page.click(value); };
  try {
    await page.click(invoiceId); await page.click("Edit draft");
    assert.equal(page.record()?.data.payment_type, null); assert.equal(page.record()?.data.income_type, null); assert.equal(page.record()?.data.tax_inclusion, null);
    await choose("Fiscal payment terms", "Credit"); assert.ok(!document.body.textContent?.includes("Complete this field before preparing issuance.")); await choose("Income type", "Other income"); await choose("Prices and tax", "Tax included"); await page.click("Save draft");
    assert.equal(page.record()?.data.payment_type, "credit"); assert.equal(page.record()?.data.income_type, 6); assert.equal(page.record()?.data.tax_inclusion, "included"); assert.equal(page.record()?.payment_state, "unknown");
    await page.click("Edit draft"); await page.click("Back"); await page.click("Add product");
    assert.equal(page.record()?.data.items.length, 0);
    await choose("Item type", "Service"); await choose("Tax treatment", "Exempt"); await page.click("Save draft");
    assert.equal(page.record()?.data.items[0].classification, "services"); assert.equal(page.record()?.data.items[0].tax_treatment, "exempt"); assert.equal(page.record()?.data.items[0].description, "");
  } finally { await page.close(); }
});
test("switching Business during real editor save aborts it and never applies a late success", async () => {
  const page = await mount({ holdCreate: true });
  try {
    await page.click("Create invoice"); await page.fill("#invoice-customer-search", "Do not show in next Business"); await page.click("Save draft");
    await page.act(async () => setChosenGrant(null)); assert.equal(page.signal()?.aborted, true); assert.equal(document.querySelector('[data-testid="invoice-editor"]'), null);
    await page.act(async () => { page.release(); await Promise.resolve(); });
    assert.ok(!document.body.textContent?.includes("Saved to this Business.")); assert.ok(document.body.textContent?.includes("no longer have access"));
  } finally { await page.close(); }
});

test("session replay keeps independent frozen commands for each account, Business and grant", async () => {
  const { createInvoiceCommandController, sessionInvoiceJournal } = await import("@/components/business-app/invoicing/invoice-command-controller");
  const { readSessionStored } = await import("@/lib/browser-storage");
  const scopes = [invoiceScope, { ...invoiceScope, businessId: "70000000-0000-4000-8000-000000000007", grantId: "80000000-0000-4000-8000-000000000008" }, { ...invoiceScope, userId: "another-account" }];
  const previousGrant = getChosenGrant(); removeSessionStored("cuadrao:invoice_commands:v1");
  const wire = { invoice: async () => { throw new TypeError("lost after commit"); }, customer: async () => savedCustomer(), prepare: async () => savedInvoice(), submit: async () => savedInvoice() };
  try {
    for (const [index, scope] of scopes.entries()) {
      setChosenGrant(scope.grantId);
      const controller = createInvoiceCommandController(scope, sessionInvoiceJournal, wire);
      assert.equal(controller.getSnapshot().kind, "idle");
      const data = incompleteInvoice(); data.notes = `Account-private draft ${index}`;
      await controller.submit({ kind: "invoice", id: null, key: `original-key-${index}`, body: { data, expected_version: null } });
      controller.dispose();
    }
    for (const [index, scope] of scopes.entries()) {
      setChosenGrant(scope.grantId);
      const reopened = createInvoiceCommandController(scope, sessionInvoiceJournal, wire), state = reopened.getSnapshot();
      assert.equal(state.kind, "failed"); if (state.kind !== "failed" || state.command?.kind !== "invoice") throw Error("expected pending draft");
      assert.equal(state.command.key, `original-key-${index}`); assert.equal(state.command.body.data.notes, `Account-private draft ${index}`);
      reopened.dispose();
    }
    const raw = JSON.parse(readSessionStored("cuadrao:invoice_commands:v1")!);
    assert.equal(raw.length, 3); assert.deepEqual(Object.keys(raw[0].scope).sort(), ["businessId", "grantId", "userId"]);
    assert.deepEqual(Object.keys(raw[0].command).sort(), ["body", "id", "key", "kind"]);
    sessionInvoiceJournal.clear(scopes[1]); assert.equal(sessionInvoiceJournal.read(scopes[0])?.kind, "invoice"); assert.equal(sessionInvoiceJournal.read(scopes[2])?.kind, "invoice");
  } finally { removeSessionStored("cuadrao:invoice_commands:v1"); setChosenGrant(previousGrant); }
});

test("actual parent entry blocks all invoice requests while Business context and selected grant disagree", async () => {
  const page = await mount({ entry: true, selectedGrant: "80000000-0000-4000-8000-000000000008" });
  try {
    assert.equal(page.calls.filter(call => call.path.includes("/business/invoices") || call.path.includes("/business/customers")).length, 0);
    assert.equal(document.querySelector('[data-testid="invoice-editor"]'), null);
    assert.equal([...document.querySelectorAll("button")].some(button => button.textContent?.trim() === "Create invoice"), false);
  } finally { await page.close(); }
});
test("actual parent entry uses the server Owner grant and permits incomplete save only after coherent selection", async () => {
  const page = await mount({ entry: true });
  try {
    await page.click("Create invoice"); await page.click("Save draft");
    assert.equal(page.creates(), 1); assert.equal(page.record()?.business_id, invoiceScope.businessId);
    assert.equal(page.record()?.data.payment_type, null);
  } finally { await page.close(); }
});

test("actual entry fails closed when actor or canonical permissions are missing", async () => {
  for (const missing of [{ missingActor: true }, { missingPermissions: true }]) {
    const page = await mount({ entry: true, ...missing });
    try { assert.equal(page.calls.length, 0); assert.equal(document.querySelector('[data-testid="connected-invoicing-workspace"]'), null); }
    finally { await page.close(); }
  }
});
