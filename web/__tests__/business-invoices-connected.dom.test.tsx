import assert from "node:assert/strict";
import { afterAll, beforeAll, mock, test } from "bun:test";
import { GlobalRegistrator } from "@happy-dom/global-registrator";
import type { BusinessContextValue } from "@/components/business-app/BusinessWorkspace";
import type { FiscalOperation, InvoiceDraft, SavedInvoice, SavedCustomer } from "@/lib/business-invoices-api";
import { invoiceId, invoiceScope, incompleteInvoice, savedInvoice, savedCustomer } from "./fixtures/business-invoice-fixture";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { removeSessionStored } from "@/lib/browser-storage";

const realFlags = { ...await import("@/lib/private-alpha-flags") };
mock.module("@/lib/private-alpha-flags", () => ({ ...realFlags, businessInvoicingEnabled: true }));

beforeAll(() => { GlobalRegistrator.register({ url: "http://localhost/biz?view=invoicing" }); Object.assign(globalThis, { IS_REACT_ACT_ENVIRONMENT: true }); });
afterAll(async () => { await GlobalRegistrator.unregister(); });
async function mount(options: { record?: SavedInvoice; loseCreate?: boolean; losePrepare?: boolean; holdCreate?: boolean; entry?: boolean; selectedGrant?: string | null; missingActor?: boolean; missingPermissions?: boolean; directory?: "loading" | "failed"; checkTaxId?: boolean; customerRecords?: SavedCustomer[]; rejectCustomerTax?: boolean; holdReads?: boolean; readFailure?: number; noPrepare?: boolean; refuse?: "prepare" | "customer"; fiscalOff?: boolean; loseCustomerCreate?: boolean; rejectFirstInvoiceCreate?: boolean } = {}) {
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
  const calls: { path: string; query: string; method: string; body: unknown; key: string | null }[] = [];
  let releaseCreate: (() => void) | undefined; let heldSignal: AbortSignal | null | undefined;
  const createdCustomers: SavedCustomer[] = structuredClone(options.customerRecords ?? []), customerByKey = new Map<string, SavedCustomer>();
  let loseCustomerCreate = options.loseCustomerCreate, rejectFirstInvoiceCreate = options.rejectFirstInvoiceCreate;
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input)), method = init?.method ?? "GET", body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path: url.pathname, query: url.search, method, body, key: new Headers(init?.headers).get("Idempotency-Key") });
    if (method === "GET" && ["/business/invoices", "/business/customers"].some(path => url.pathname.endsWith(path))) {
      if (options.holdReads) return new Promise<Response>(() => {});
      if (options.readFailure) return Response.json({ code: "synthetic_read_failure" }, { status: options.readFailure });
    }
    if (url.pathname.endsWith("/business/invoices") && method === "GET") return Response.json({ items: record ? [record] : [], total: record ? 1 : 0, page: 1, page_size: 25, stage_counts: { draft: record && !record.operation ? 1 : 0, issued: record?.operation?.state.legal === "ACCEPTED" ? 1 : 0, uncertain: record?.operation?.state.submission === "unknown" ? 1 : 0 }, summaries: [], query_version: "synthetic-version" });
    if (url.pathname.endsWith("/business/customers") && method === "GET") return Response.json({ items: createdCustomers, total: createdCustomers.length, page: 1, page_size: 25 });
    if (options.refuse === "customer" && url.pathname.includes("/business/customers") && method === "POST") return Response.json({ code: "business_unavailable", request_id: "customer-ref-0001" }, { status: 404 });
    if (options.refuse === "prepare" && url.pathname.endsWith("/prepare")) return Response.json({ code: "business_record_not_found", request_id: "prepare-ref-0001" }, { status: 404 });
    if (url.pathname.includes("/business/customers") && ["POST", "PUT"].includes(method)) {
      if (options.rejectCustomerTax && !/^(?:[0-9]{9}|[0-9]{11})$/.test(body.data.tax_id)) return Response.json({ code: "customer_invalid", context: { field_errors: { tax_id: "tax_id" } } }, { status: 422 });
      if (method === "PUT") { const index = createdCustomers.findIndex(customer => url.pathname.endsWith(`/${customer.id}`)); assert.ok(index >= 0); assert.equal(body.expected_version, createdCustomers[index].version); createdCustomers[index] = { ...createdCustomers[index], data: body.data, version: createdCustomers[index].version + 1 }; return Response.json(createdCustomers[index]); }
      const key = new Headers(init?.headers).get("Idempotency-Key") ?? "";
      let customer = customerByKey.get(key);
      if (!customer) { customer = { ...savedCustomer(), id: `50000000-0000-4000-8000-${String(createdCustomers.length + 5).padStart(12, "0")}`, data: body.data }; customerByKey.set(key, customer); createdCustomers.push(customer); }
      if (loseCustomerCreate) { loseCustomerCreate = false; throw new TypeError("synthetic customer response lost after commit"); }
      return Response.json(customer);
    }
    if (url.pathname.endsWith("/business/invoices") && method === "POST") {
      if (rejectFirstInvoiceCreate) { rejectFirstInvoiceCreate = false; return Response.json({ code: "invoice_invalid", context: { field_errors: {} } }, { status: 422 }); }
      if (!record) { record = savedInvoice(body.data); creates++; }
      if (options.holdCreate) { heldSignal = init?.signal; await new Promise<void>(resolve => { releaseCreate = resolve; }); }
      if (loseCreate) { loseCreate = false; throw new TypeError("synthetic response lost after commit"); }
      return Response.json(record);
    }
    if (url.pathname.endsWith(`/business/invoices/${invoiceId}`) && method === "PUT" && record) { record = { ...record, version: record.version + 1, data: body.data, field_errors: options.checkTaxId ? /^(?:[0-9]{9}|[0-9]{11})$/.test(body.data.customer_input.tax_id) ? {} : { "customer_input.tax_id": "tax_id" } : record.field_errors, amounts: body.data.tax_inclusion === "included" ? null : record.amounts }; return Response.json(record); }
    if (options.fiscalOff && ["/prepare", "/submit"].some(suffix => url.pathname.endsWith(suffix))) return Response.json({ type: "https://api.argus.app/problems/http-error", title: "Request Failed", status: 404, detail: "fiscal_sandbox_unavailable", code: "http_error", request_id: "synthetic-request" }, { status: 404 });
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
  let currentContext: BusinessContextValue = options.directory ? { ...context, chosen: null, directoryStatus: options.directory } : context;
  const host = document.createElement("div"); document.body.append(host); let root = createRoot(host);
  const render = async () => { await act(async () => { root.render(<StrictMode><I18nextProvider i18n={i18n}><BusinessContext.Provider value={currentContext}>{options.entry ? <BusinessPanel /> : <ConnectedInvoicingWorkspace scope={invoiceScope} business="Synthetic Business" capabilities={{ prepare: !options.noPrepare, issue: false, download: true }} />}</BusinessContext.Provider></I18nextProvider></StrictMode>); }); };
  await render();
  const button = (text: string) => { const found = [...document.querySelectorAll<HTMLButtonElement>("button")].find(node => node.textContent?.trim() === text && !node.closest("[hidden]")); assert.ok(found, `missing button ${text}`); return found; };
  const click = async (text: string) => { await act(async () => button(text).click()); };
  const fill = async (selector: string, value: string) => { const input = document.querySelector<HTMLInputElement>(selector); assert.ok(input); await act(async () => { Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, value); input.dispatchEvent(new Event("input", { bubbles: true })); }); };
  const openRow = async () => { const link = document.querySelector<HTMLButtonElement>("tbody tr td:first-child button"); assert.ok(link, "missing invoice row link"); await act(async () => link.click()); };
  const reopen = async () => { await act(async () => root.unmount()); root = createRoot(host); await render(); };
  return { calls, click, fill, button, act, reopen, openRow, customerRecords: () => createdCustomers, advanceAccepted: () => { if (record?.operation) record = { ...record, operation: { ...record.operation, state: { ...record.operation.state, submission: "identified", processing: "FINISHED", legal: "ACCEPTED", xml: "available", pdf: "available" } } }; }, resolveDirectory: async () => { currentContext = { ...context, directoryStatus: "ready" }; await render(); }, release: () => releaseCreate?.(), signal: () => heldSignal, record: () => record, creates: () => creates, prepareEffects: () => prepareEffects, async close() { await act(async () => root.unmount()); host.remove(); globalThis.fetch = previousFetch; setChosenGrant(previousGrant); if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock; removeSessionStored("cuadrao:invoice_commands:v1"); } };
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
    await page.openRow(); assert.ok(document.body.textContent?.includes("Preparing this invoice locks its details.")); await page.click("Prepare issuance"); await page.click("Retry the same request");
    const prepares = page.calls.filter(call => call.path.endsWith("/prepare")); assert.equal(prepares.length, 2); assert.deepEqual(prepares[1], prepares[0]); assert.equal(page.prepareEffects(), 1);
    assert.equal(page.calls.some(call => call.path.endsWith("/submit")), false); assert.ok(document.body.textContent?.includes("Prepared, not issued")); assert.equal(page.record()?.payment_state, "unknown"); assert.equal(page.record()?.delivery_state, "not_sent");
  } finally { await page.close(); }
});

test("saved decimal totals disappear after local price edits and included-tax save remains unknown", async () => {
  const data = { ...incompleteInvoice(), customer_input: { ...incompleteInvoice().customer_input, name: "Saved contact snapshot" }, issued_on: "2026-10-27", due_on: "2026-10-27", payment_type: "cash" as const, income_type: 1 as const, tax_inclusion: "excluded" as const, items: [{ id: "price-item", description: "Saved service", quantity: "1", price: "100.01", discount: "0", tax: "0", classification: "services" as const, tax_treatment: "exempt" as const }] };
  const page = await mount({ record: { ...savedInvoice(data), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } } });
  try {
    await page.openRow(); await page.click("Edit draft"); await page.click("Next");
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
    await page.reopen(); await page.openRow(); await page.click("Edit draft"); await page.click("Next"); assert.equal(document.querySelector<HTMLInputElement>("#invoice-price-item-price")?.value, "200.020");
  } finally { await page.close(); }
});

test("the five fiscal choices remain blank until explicit selection and incomplete saves retain them", async () => {
  const page = await mount({ record: savedInvoice() });
  const choose = async (label: string, value: string) => { const span = [...document.querySelectorAll("span")].find(node => node.textContent === label); assert.ok(span, label); const button = span.parentElement?.querySelector("button"); assert.ok(button); await page.act(async () => button.click()); await page.click(value); };
  try {
    await page.openRow(); await page.click("Edit draft");
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
    assert.ok(!document.body.textContent?.includes("Saved to this Business.")); assert.ok(document.body.textContent?.includes("do not have access"));
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

test("actual direct entry waits for a delayed directory without denial or invoice requests", async () => {
  const page = await mount({ entry: true, directory: "loading" });
  try {
    assert.ok(document.querySelector('[role="status"]')?.textContent?.includes("Loading"));
    assert.ok(!document.body.textContent?.includes("You do not have access")); assert.equal(page.calls.length, 0);
    await page.resolveDirectory(); await page.click("Create invoice"); assert.ok(document.querySelector('[data-testid="invoice-editor"]'));
  } finally { await page.close(); }
});
test("terminal directory failure offers retry without an endless loading state or access claim", async () => {
  const page = await mount({ entry: true, directory: "failed" });
  try { assert.ok(document.querySelector('[role="alert"]')); assert.ok(!document.body.textContent?.includes("You do not have access")); assert.equal(page.calls.length, 0); assert.ok(page.button("Retry")); }
  finally { await page.close(); }
});
test("connected customers accept backend name/address limits and visibly reject tax33 before sending", async () => {
  const page = await mount();
  try {
    await page.click("Customers"); await page.click("Add customer");
    assert.equal(document.querySelector<HTMLInputElement>("#customer-name")?.maxLength, 200); assert.equal(document.querySelector<HTMLInputElement>("#customer-address")?.maxLength, 500); assert.equal(document.querySelector<HTMLInputElement>("#customer-taxId")?.maxLength, 32);
    await page.fill("#customer-name", "N".repeat(180)); await page.fill("#customer-address", "A".repeat(400)); await page.fill("#customer-taxId", "x".repeat(33)); await page.click("Save customer");
    assert.equal(page.calls.filter(call => call.method === "POST").length, 0); assert.equal(document.querySelector<HTMLInputElement>("#customer-taxId")?.getAttribute("aria-invalid"), "true");
    await page.fill("#customer-taxId", ""); await page.click("Save customer");
    const writes = page.calls.filter(call => call.method === "POST" && call.path.endsWith("/customers")); assert.equal(writes.length, 1);
    const body = writes[0].body as { data: { name: string; address: string } }; assert.equal(body.data.name, "N".repeat(180)); assert.equal(body.data.address, "A".repeat(400));
    await page.reopen(); await page.click("Customers"); await page.click("N".repeat(180)); assert.equal(document.querySelector<HTMLInputElement>("#customer-address")?.value, "A".repeat(400));
  } finally { await page.close(); }
});
test("a new connected draft does not display the internal English new reference", async () => {
  const page = await mount(); try { await page.click("Create invoice"); assert.ok(!document.body.textContent?.includes("· new")); assert.equal([...document.querySelectorAll('[class*="documentHeader"] p')].some(node => node.textContent === "new"), false); }
  finally { await page.close(); }
});

test("confirmed fiscal refresh requeries the list counts and rows without closing detail or resetting query", async () => {
  const operation = preparedOperation(); operation.state.submission = "unknown";
  const page = await mount({ record: { ...savedInvoice(), operation } });
  try {
    await page.fill('input[type="search"]', "E32"); await page.click(operation.number); const before = page.calls.filter(call => call.path.endsWith("/invoices") && call.method === "GET").length;
    page.advanceAccepted(); await page.click("Check fiscal status");
    assert.ok(page.calls.filter(call => call.path.endsWith("/invoices") && call.method === "GET").length > before);
    const issuedTab = [...document.querySelectorAll('[role="tab"]')].find(node => node.textContent?.startsWith("Issued")); assert.equal(issuedTab?.textContent, "Issued1");
    assert.equal(document.querySelector('tbody tr td:last-child')?.textContent, "Issued"); assert.ok(document.querySelector('[role="dialog"]')); assert.equal(document.querySelector<HTMLInputElement>('input[type="search"]')?.value, "E32");
  } finally { await page.close(); }
});

test("connected fiscal customer digits survive blur, Save and immutable prepare without preview formatting", async () => {
  for (const digits of ["131793891", "00101234567"]) {
    const data: InvoiceDraft = { ...incompleteInvoice(), document_type: "E31", customer_input: { ...incompleteInvoice().customer_input, name: "Fiscal customer" }, payment_type: "cash", income_type: 1, tax_inclusion: "excluded", issued_on: "2026-10-27", due_on: "2026-10-27", items: [{ id: "fiscal-item", description: "Service", quantity: "1", price: "100.01", discount: "0", tax: "0", classification: "services", tax_treatment: "exempt" }] };
    const page = await mount({ record: { ...savedInvoice(data), field_errors: { "customer_input.tax_id": "required" } }, checkTaxId: true });
    try {
      await page.openRow(); await page.click("Edit draft"); await page.fill("#invoice-taxId", digits);
      await page.act(async () => { const input = document.querySelector<HTMLInputElement>("#invoice-taxId")!; input.focus(); input.blur(); });
      await page.click("Save draft"); assert.equal(page.record()?.data.customer_input.tax_id, digits); await page.click("Prepare issuance");
      assert.equal(page.prepareEffects(), 1); assert.equal(page.record()?.data.customer_input.tax_id, digits);
      const prepared = page.calls.find(call => call.path.endsWith("/prepare")); assert.deepEqual(prepared?.body, { expected_version: 2 });
    } finally { await page.close(); }
  }
});

test("manually formatted fiscal ID remains an exact incomplete draft with a visible server field error", async () => {
  const page = await mount({ record: { ...savedInvoice(), field_errors: { "customer_input.tax_id": "required" } }, checkTaxId: true });
  try {
    await page.openRow(); await page.click("Edit draft"); await page.fill("#invoice-customer-search", "Draft customer"); await page.click("Add customer · Draft customer"); await page.fill("#invoice-taxId", "131-79389-1"); await page.click("Save draft");
    assert.equal(page.record()?.data.customer_input.tax_id, "131-79389-1"); assert.equal(page.button("Prepare issuance").disabled, true);
    await page.click("Edit draft"); assert.equal(document.querySelector<HTMLInputElement>("#invoice-taxId")?.value, "131-79389-1"); assert.equal(document.querySelector<HTMLInputElement>("#invoice-taxId")?.getAttribute("aria-invalid"), "true");
  } finally { await page.close(); }
});

test("correcting a server-rejected customer field allows a second explicit Save without changing target or version", async () => {
  for (const existing of [false, true]) {
    const original = savedCustomer(), page = await mount({ customerRecords: existing ? [original] : [], rejectCustomerTax: true });
    try {
      await page.click("Customers"); await page.click(existing ? original.data.name : "Add customer");
      await page.fill("#customer-name", "Keep this contact name"); await page.fill("#customer-address", "Keep this full address"); await page.fill("#customer-taxId", "131-793891"); await page.click("Save customer");
      const writes = () => page.calls.filter(call => ["POST", "PUT"].includes(call.method) && call.path.includes("/customers"));
      assert.equal(writes().length, 1); assert.equal(page.customerRecords().length, existing ? 1 : 0); assert.equal(document.querySelector<HTMLInputElement>("#customer-taxId")?.getAttribute("aria-invalid"), "true");
      await page.click("Save customer"); assert.equal(writes().length, 1);
      await page.fill("#customer-taxId", "000000000"); await page.click("Save customer"); assert.equal(writes().length, 1); assert.equal(document.querySelector<HTMLInputElement>("#customer-taxId")?.getAttribute("aria-invalid"), "true");
      await page.fill("#customer-taxId", "131793891"); await page.click("Save customer");
      assert.equal(writes().length, 2); assert.equal(writes()[0].path, writes()[1].path); assert.notEqual(writes()[0].key, writes()[1].key);
      for (const write of writes()) assert.equal((write.body as { expected_version: number | null }).expected_version, existing ? original.version : null);
      const records = page.customerRecords(); assert.equal(records.length, 1); assert.equal(records[0].data.tax_id, "131793891"); assert.equal(records[0].data.name, "Keep this contact name"); assert.equal(records[0].data.address, "Keep this full address"); if (existing) { assert.equal(records[0].id, original.id); assert.equal(records[0].version, original.version + 1); }
    } finally { await page.close(); }
  }
});

test("connected empty invoices reuse the approved illustration and one guarded create action", async () => {
  const page = await mount();
  try {
    const image = document.querySelector('img[width="144"]');
    assert.ok(image?.getAttribute("src")?.includes("first-invoice"), "approved first-invoice artwork is shown");
    assert.equal(document.querySelector("h3")?.textContent, "Create your first invoice");
    assert.equal([...document.querySelectorAll("button")].filter(button => button.textContent?.trim() === "Create invoice").length, 1);
    await page.click("Create invoice");
    assert.ok(document.querySelector('[data-testid="invoice-editor"]'));
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
});

test("connected empty customer directory reuses its approved illustration and explicit add action", async () => {
  const page = await mount();
  try {
    await page.click("Customers");
    assert.ok(document.querySelector('img[width="144"]')?.getAttribute("src")?.includes("customer-directory"));
    assert.equal([...document.querySelectorAll("button")].filter(button => button.textContent?.trim() === "Add customer").length, 1);
    await page.click("Add customer");
    assert.ok(document.querySelector('#customer-name'));
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
});

test("illustrated connected empty state keeps prepare permission and does not mask pending or failed reads", async () => {
  const denied = await mount({ noPrepare: true });
  try {
    assert.ok(denied.button("Create invoice").disabled);
    assert.ok(document.querySelector('img[width="144"]'));
  } finally { await denied.close(); }
  for (const options of [{ holdReads: true }, { readFailure: 503 }, { readFailure: 403 }]) {
    const page = await mount(options);
    try {
      assert.equal(document.querySelector('img[width="144"]'), null);
      assert.ok(document.querySelector(options.holdReads ? '[role="status"]' : '[role="alert"]'));
    } finally { await page.close(); }
  }
});

test("filtered and archived empty results stay compact and never claim the first invoice", async () => {
  const page = await mount();
  try {
    await page.fill('input[aria-label="Search customer, invoice or note…"]', "unmatched");
    assert.equal(document.querySelector("h3")?.textContent, "No invoices match these filters");
    assert.ok(document.querySelector('img[width="88"]'));
    await page.fill('input[aria-label="Search customer, invoice or note…"]', "");
    const draft = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(tab => tab.textContent?.startsWith("Draft"));
    assert.ok(draft);
    await page.act(async () => draft.click());
    assert.equal(document.querySelector("h3")?.textContent, "No invoices match these filters");
    assert.ok(document.querySelector('img[width="88"]'));
    await page.click("Customers");
    await page.fill('input[aria-label="Search customers"]', "unmatched");
    assert.equal(document.querySelector("h3")?.textContent, "No customers match this search.");
    assert.ok(document.querySelector('img[width="88"]'));
    await page.fill('input[aria-label="Search customers"]', "");
    await page.click("Active");
    assert.equal(document.querySelector("h3")?.textContent, "No archived customers");
    assert.ok(document.querySelector('img[width="88"]'));
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
});

test("empty invoice reset clears real filters and period while preserving stage and page size", async () => {
  const page = await mount();
  try {
    const draft = [...document.querySelectorAll<HTMLButtonElement>('[role="tab"]')].find(tab => tab.textContent?.startsWith("Draft"));
    assert.ok(draft); await page.act(async () => draft.click());
    assert.equal([...document.querySelectorAll("button")].some(button => button.textContent?.trim() === "Clear filters"), false);
    await page.click("25 per page"); await page.click("50 per page");
    const date = [...document.querySelectorAll<HTMLButtonElement>('button[aria-haspopup="dialog"]')].find(button => button.textContent?.trim() === "All");
    assert.ok(date); await page.act(async () => date.click());
    await page.click("Last 7 days"); await page.click("Confirm period");
    await page.click("All currencies"); await page.click("USD");
    await page.fill('input[aria-label="Search customer, invoice or note…"]', "unmatched");
    const before = new URLSearchParams(page.calls.filter(call => call.path.endsWith("/business/invoices") && call.method === "GET").at(-1)!.query);
    assert.equal(before.get("currency"), "USD"); assert.ok(before.get("date_from")); assert.ok(before.get("date_to"));
    await page.click("Clear filters");
    const after = new URLSearchParams(page.calls.filter(call => call.path.endsWith("/business/invoices") && call.method === "GET").at(-1)!.query);
    assert.equal(after.get("search"), ""); assert.equal(after.get("currency"), null); assert.equal(after.get("date_from"), null); assert.equal(after.get("date_to"), null);
    assert.equal(after.get("page"), "1"); assert.equal(after.get("page_size"), "50"); assert.equal(after.get("stage"), "draft"); assert.equal(after.get("sort"), before.get("sort"));
    assert.ok([...document.querySelectorAll("button")].some(button => button.textContent?.trim() === "All" && button.hasAttribute("aria-haspopup")));
    assert.equal([...document.querySelectorAll("button")].some(button => button.textContent?.trim() === "Clear filters"), false);
  } finally { await page.close(); }
});

test("customer no-match reset clears search while retaining archived selection", async () => {
  const page = await mount();
  try {
    await page.click("Customers"); await page.click("Active");
    assert.equal([...document.querySelectorAll("button")].some(button => button.textContent?.trim() === "Clear search"), false);
    await page.fill('input[aria-label="Search customers"]', "unmatched");
    await page.click("Clear search");
    const query = new URLSearchParams(page.calls.filter(call => call.path.endsWith("/business/customers") && call.method === "GET").at(-1)!.query);
    assert.equal(query.get("search"), ""); assert.equal(query.get("archived"), "true"); assert.equal(query.get("page"), "1");
    assert.equal(document.querySelector("h3")?.textContent, "No archived customers");
    assert.equal(document.querySelector('img[width="88"]')?.parentElement?.querySelectorAll("button").length, 0);
  } finally { await page.close(); }
});

test("connected populated rows reuse approved status badges without turning fiscal acceptance into payment", async () => {
  const prepared = preparedOperation();
  const cases = [
    { operation: null, state: "draft", label: "Drafts" },
    { operation: prepared, state: "prepare_state", label: "Prepared, not issued" },
    { operation: { ...prepared, state: { ...prepared.state, submission: "unknown" } }, state: "uncertain", label: "Uncertain" },
    { operation: { ...prepared, state: { ...prepared.state, submission: "identified", legal: "ACCEPTED" } }, state: "issued", label: "Issued" },
    { operation: { ...prepared, state: { ...prepared.state, submission: "identified", legal: "REJECTED" } }, state: "rejected", label: "Rejected" },
    { operation: { ...prepared, state: { ...prepared.state, submission: "identified" } }, state: "processing", label: "Processing" },
  ] satisfies { operation: SavedInvoice["operation"]; state: string; label: string }[];
  for (const item of cases) {
    const data = incompleteInvoice(); data.customer_input.name = "A long synthetic customer name that needs the approved full-name tooltip";
    const record = { ...savedInvoice(data), operation: item.operation, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } };
    const page = await mount({ record });
    try {
      const row = document.querySelector("tbody tr"); assert.ok(row);
      const badge = row.querySelector('td:last-child > span[class*="badge"]');
      assert.ok(badge, `desktop ${item.state} badge`); assert.equal(badge.getAttribute("data-state"), item.state); assert.equal(badge.textContent, item.label);
      assert.equal(row.children[1].getAttribute("title"), data.customer_input.name);
      assert.equal(row.children[5].textContent, "100.01"); assert.equal(row.children[6].textContent, "-");
      const mobile = document.querySelector('[class*="phoneList"] > button'); assert.ok(mobile);
      const wrapper = mobile.children[2]; assert.equal(wrapper.tagName, "SPAN"); assert.equal(wrapper.className.includes("badge"), false);
      const mobileBadge = wrapper.querySelector('span[class*="badge"]'); assert.ok(mobileBadge); assert.equal(mobileBadge.getAttribute("data-state"), item.state); assert.equal(mobileBadge.textContent, item.label);
      assert.equal(page.record()?.payment_state, "unknown"); assert.equal(page.record()?.outstanding_amount, null);
    } finally { await page.close(); }
  }
});

test("connected invoice rows and their nested buttons open one authoritative dossier and show selection", async () => {
  const data = incompleteInvoice(); data.customer_input.name = "Synthetic row customer";
  const page = await mount({ record: savedInvoice(data) });
  try {
    const reads = () => page.calls.filter(call => call.method === "GET" && call.path.endsWith(`/invoices/${invoiceId}`)).length;
    const row = () => { const node = document.querySelector<HTMLTableRowElement>("tbody tr"); assert.ok(node); return node; };
    assert.equal(row().getAttribute("data-selected"), "false");
    const customerCell = row().children[1]; assert.ok(customerCell instanceof HTMLElement);
    await page.act(async () => customerCell.click());
    assert.equal(reads(), 1); assert.equal(row().getAttribute("data-selected"), "true"); assert.ok(document.querySelector('[role="dialog"]'));
    const close = document.querySelector<HTMLButtonElement>('[role="dialog"] button[aria-label="Close"]'); assert.ok(close); await page.act(async () => close.click());
    assert.equal(row().getAttribute("data-selected"), "false");
    const button = row().querySelector<HTMLButtonElement>("td:first-child button"); assert.ok(button);
    await page.act(async () => { button.focus(); button.click(); });
    assert.equal(reads(), 2, "nested button must not bubble into a second GET"); assert.equal(row().getAttribute("data-selected"), "true");
    await page.click("Edit draft"); assert.equal(row().getAttribute("data-selected"), "false");
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
});

const readyDraft = (): InvoiceDraft => ({ ...incompleteInvoice(), customer_input: { ...incompleteInvoice().customer_input, name: "Synthetic ready customer" }, payment_type: "cash", income_type: 1, tax_inclusion: "excluded", issued_on: "2026-10-27", due_on: "2026-10-27", items: [{ id: "item-one", description: "Service", quantity: "1", price: "100.01", discount: "0", tax: "0", classification: "services", tax_treatment: "exempt" }] });
test("with fiscal issuance off, Prepare issuance becomes a disabled note and editing stays usable across reload", async () => {
  const page = await mount({ record: { ...savedInvoice(readyDraft()), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } }, fiscalOff: true }); try {
    await page.openRow(); await page.click("Prepare issuance");
    assert.equal(page.calls.filter(call => call.path.endsWith("/prepare")).length, 1);
    assert.ok(document.body.textContent?.includes("Fiscal issuance is not available yet."));
    assert.equal(document.body.textContent?.includes("Retry the same request"), false);
    assert.equal(document.body.textContent?.includes("We could not confirm whether it was saved"), false);
    assert.equal(page.button("Prepare issuance").disabled, true);
    assert.ok(document.body.textContent?.includes("Issuance is not available yet."));
    assert.ok(document.body.textContent?.includes("If you think this is a mistake, email us at hola@cuadrao.ai."), "the unavailable state names a way out");
    assert.equal(document.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. syntheti"), true, "the unavailable state shows its reference");
    assert.equal(sessionStorage.getItem("cuadrao:invoice_commands:v1"), null);
    await page.click("Edit draft"); await page.click("Save draft");
    assert.equal(page.calls.filter(call => call.method === "PUT" && call.path.endsWith(`/business/invoices/${invoiceId}`)).length, 1, "a later save reaches the server");
    assert.ok(document.body.textContent?.includes("Saved to this Business."));
    await page.reopen(); await page.openRow(); await page.click("Edit draft"); await page.click("Save draft");
    assert.equal(page.calls.filter(call => call.method === "PUT").length, 2, "a reload leaves saving usable");
  } finally { await page.close(); }
});

test("a refused prepare says what was refused, shows its reference and the contact line, with no Retry", async () => {
  const page = await mount({ record: { ...savedInvoice(readyDraft()), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } }, refuse: "prepare" }); try {
    await page.openRow(); await page.click("Prepare issuance");
    const text = document.body.textContent ?? "";
    assert.ok(text.includes("Cuadrao refused to prepare this invoice. Your draft is kept;"));
    assert.ok(text.includes("If you think this is a mistake, email us at hola@cuadrao.ai."));
    assert.ok(document.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. prepare-"));
    assert.equal(text.includes("Retry the same request"), false); assert.equal(sessionStorage.getItem("cuadrao:invoice_commands:v1"), null);
  } finally { await page.close(); }
});
test("a refused customer save keeps draft wording out of the Customer form and still names a way out", async () => {
  const page = await mount({ refuse: "customer" }); try {
    await page.click("Customers"); await page.click("Add customer"); await page.fill("#customer-name", "Refused customer"); await page.click("Save customer");
    const text = document.body.textContent ?? "";
    assert.ok(text.includes("Cuadrao refused to save this customer."));
    assert.equal(text.includes("draft is kept"), false, "no draft exists in the Customer form");
    assert.ok(text.includes("If you think this is a mistake, email us at hola@cuadrao.ai."));
    assert.ok(document.querySelector('[data-testid="error-reference"]')?.textContent?.includes("Ref. customer"));
  } finally { await page.close(); }
});

const uuidText = /[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i;
test("a saved draft is named by its draft label and no UUID reaches the table, phone list, dossier or editor", async () => {
  const data = readyDraft(), page = await mount({ record: { ...savedInvoice(data), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } } }); try {
    const link = document.querySelector("tbody tr td:first-child button"); assert.equal(link?.textContent, "Draft · Oct 27, 2026");
    assert.equal(uuidText.test(document.body.textContent ?? ""), false, "list");
    await page.openRow(); assert.equal(uuidText.test(document.body.textContent ?? ""), false, "dossier");
    assert.ok(document.querySelector('[data-testid="invoice-customer-document"]')?.textContent?.includes("Draft · Oct 27, 2026"));
    await page.click("Edit draft"); assert.equal(uuidText.test(document.body.textContent ?? ""), false, "editor");
    assert.ok(document.querySelector('[data-testid="invoice-editor"]')?.textContent?.includes("Draft · Oct 27, 2026"));
    assert.equal(uuidText.test(document.querySelector('[class*="phoneList"]')?.textContent ?? ""), false, "phone list");
  } finally { await page.close(); }
});
test("a prepared invoice keeps its fiscal number as identity", async () => {
  const page = await mount({ record: { ...savedInvoice(readyDraft()), field_errors: {}, operation: preparedOperation() } }); try {
    assert.equal(document.querySelector("tbody tr td:first-child button")?.textContent, "E320000000001");
    assert.equal(uuidText.test(document.body.textContent ?? ""), false);
  } finally { await page.close(); }
});
test("the invoice dossier lists payments, corrections and delivery as static unavailable blocks and the editor review says nothing is sent", async () => {
  const page = await mount({ record: { ...savedInvoice(readyDraft()), field_errors: {}, amounts: { subtotal: "100.01", discount: "0.00", tax: "0.00", total: "100.01" } } }); try {
    await page.openRow();
    const blocks = document.querySelector('[data-testid="invoice-unavailable-blocks"]'); assert.ok(blocks);
    for (const text of ["Payments", "Corrections", "Delivery", "Payments cannot be recorded here yet.", "Not available yet.", "Sending is not available yet."]) assert.ok(blocks.textContent?.includes(text), text);
    assert.equal(blocks.querySelectorAll("button, a, input").length, 0, "blocks are static");
    await page.click("Edit draft"); await page.click("Next"); await page.click("Next"); await page.click("Next");
    assert.ok(document.querySelector('[data-testid="invoice-editor"]')?.textContent?.includes("Saved only; nothing is sent."));
    assert.equal(document.body.textContent?.includes("Saved for this session"), false);
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
});
test("the connected first-use state offers the three setup cards as navigation only, with no readiness marks", async () => {
  const page = await mount(); try {
    const cards = document.querySelector('[data-testid="invoice-setup-cards"]'); assert.ok(cards);
    assert.deepEqual([...cards.querySelectorAll("strong")].map(node => node.textContent), ["Business details", "Add a customer", "Prepare your first invoice"]);
    assert.equal(cards.querySelector("svg[class*='check'], [aria-checked], [role='checkbox']"), null);
    await page.act(async () => cards.querySelectorAll("button")[1].click()); assert.ok(document.querySelector("#customer-name"));
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0);
  } finally { await page.close(); }
  const filtered = await mount({ record: savedInvoice() }); try { assert.equal(document.querySelector('[data-testid="invoice-setup-cards"]'), null, "populated list has no setup cards"); } finally { await filtered.close(); }
  const readOnly = await mount({ noPrepare: true }); try {
    const guarded = [...document.querySelectorAll<HTMLButtonElement>('[data-testid="invoice-setup-cards"] button')].map(node => node.disabled);
    assert.deepEqual(guarded, [false, true, true]);
  } finally { await readOnly.close(); }
});
test("Settings sets row height on the table and sends the newest or oldest sort to the server", async () => {
  const page = await mount({ record: savedInvoice() }); try {
    const sorts = () => page.calls.filter(call => call.method === "GET" && call.path.endsWith("/business/invoices")).map(call => new URLSearchParams(call.query).get("sort"));
    assert.equal(sorts().at(-1), "newest");
    const frame = () => document.querySelector('[class*="tableFrame"]'); assert.equal(frame()?.getAttribute("data-density"), "normal");
    await page.click("Settings");
    const radio = (name: string) => [...document.querySelectorAll<HTMLElement>('[role="radio"], button')].find(node => node.textContent?.trim() === name); 
    const compact = radio("Compact"); assert.ok(compact); await page.act(async () => compact.click());
    assert.equal(frame()?.getAttribute("data-density"), "compact");
    assert.equal(page.calls.filter(call => call.method !== "GET").length, 0, "density is client-only");
    const oldest = radio("Oldest"); assert.ok(oldest); await page.act(async () => oldest.click());
    assert.equal(sorts().at(-1), "oldest");
    const newest = radio("Newest"); assert.ok(newest); await page.act(async () => newest.click());
    assert.equal(sorts().at(-1), "newest");
  } finally { await page.close(); }
});
test("Scheduled is a visibly unavailable tab with a calendar empty state, no create and no requests", async () => {
  const page = await mount({ record: savedInvoice() }); try {
    const reads = page.calls.length;
    await page.click("Scheduled");
    const view = document.querySelector('[data-testid="schedules-unavailable"]'); assert.ok(view);
    assert.ok(view.querySelector('img[src*="schedule-calendar"]'), "calendar artwork");
    assert.ok(view.textContent?.includes("Scheduled invoices are not available yet."));
    assert.equal(view.querySelectorAll("button").length, 0, "no create or other action");
    assert.equal(document.querySelector('input[type="search"]'), null);
    assert.equal(page.calls.length, reads, "no request for a schedules list");
    await page.click("Invoices"); assert.ok(document.querySelector("tbody tr"));
  } finally { await page.close(); }
});
const customerPosts = (page: Awaited<ReturnType<typeof mount>>) => page.calls.filter(call => call.method === "POST" && call.path.endsWith("/business/customers"));
const invoicePosts = (page: Awaited<ReturnType<typeof mount>>) => page.calls.filter(call => call.method === "POST" && call.path.endsWith("/business/invoices"));
async function addNewCustomer(page: Awaited<ReturnType<typeof mount>>, name: string) {
  await page.click("Create invoice"); await page.fill("#invoice-customer-search", name);
  const option = [...document.querySelectorAll<HTMLElement>('[role="option"]')].find(node => node.textContent?.startsWith("Add customer")); assert.ok(option, "add customer option");
  await page.act(async () => option.click());
}
test("Add customer in the editor saves a registry customer through an idempotent POST before the draft links to it", async () => {
  const page = await mount(); try {
    await addNewCustomer(page, "Taller Nuevo"); await page.click("Save draft");
    const [customerPost] = customerPosts(page); assert.equal(customerPosts(page).length, 1); assert.ok(customerPost.key, "customer POST carries an idempotency key");
    assert.equal((customerPost.body as { data: { name: string } }).data.name, "Taller Nuevo");
    const saved = page.customerRecords(); assert.equal(saved.length, 1);
    assert.equal(page.record()?.data.customer_id, saved[0].id, "the draft links to the persisted customer");
    assert.equal(page.record()?.data.customer_input.name, "Taller Nuevo");
    assert.ok(page.calls.indexOf(customerPost) < page.calls.indexOf(invoicePosts(page)[0]), "customer is persisted first");
    await page.reopen(); await page.click("Customers");
    assert.ok(document.body.textContent?.includes("Taller Nuevo"), "reload shows the same customer"); assert.equal(page.customerRecords().length, 1);
  } finally { await page.close(); }
});
test("a lost customer response retries the same key and never creates a duplicate customer or invoice", async () => {
  const page = await mount({ loseCustomerCreate: true }); try {
    await addNewCustomer(page, "Taller Retry"); await page.click("Save draft");
    assert.equal(invoicePosts(page).length, 0, "the draft waits for the customer");
    await page.click("Retry the same request");
    const posts = customerPosts(page); assert.equal(posts.length, 2); assert.equal(posts[1].key, posts[0].key); assert.deepEqual(posts[1].body, posts[0].body);
    assert.equal(page.customerRecords().length, 1); assert.equal(invoicePosts(page).length, 1); assert.equal(page.record()?.data.customer_id, page.customerRecords()[0].id);
  } finally { await page.close(); }
});
test("a rejected draft save after the customer was created reuses that customer on the next Save", async () => {
  const page = await mount({ rejectFirstInvoiceCreate: true }); try {
    await addNewCustomer(page, "Taller Segundo"); await page.click("Save draft");
    assert.equal(customerPosts(page).length, 1); assert.equal(invoicePosts(page).length, 1); assert.equal(page.record(), null);
    await page.click("Save draft");
    assert.equal(customerPosts(page).length, 1, "no second customer"); assert.equal(page.customerRecords().length, 1);
    assert.equal(page.record()?.data.customer_id, page.customerRecords()[0].id);
  } finally { await page.close(); }
});
test("a rejected new customer keeps the editor open, saves no draft and marks the field", async () => {
  const page = await mount({ rejectCustomerTax: true }); try {
    await addNewCustomer(page, "Taller Rechazado");
    const tax = document.querySelector<HTMLInputElement>("#invoice-taxId"); assert.ok(tax);
    await page.fill("#invoice-taxId", "33"); await page.click("Save draft");
    assert.equal(invoicePosts(page).length, 0); assert.equal(page.customerRecords().length, 0);
    assert.ok(document.querySelector('[data-testid="invoice-editor"]')); assert.ok(document.body.textContent?.includes("The new customer was not saved."));
  } finally { await page.close(); }
});
