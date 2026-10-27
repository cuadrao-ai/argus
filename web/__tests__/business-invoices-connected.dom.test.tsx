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
async function mount(options: { record?: SavedInvoice; loseCreate?: boolean; losePrepare?: boolean; holdCreate?: boolean; entry?: boolean; selectedGrant?: string | null; missingActor?: boolean; missingPermissions?: boolean; directory?: "loading" | "failed"; checkTaxId?: boolean; customerRecords?: SavedCustomer[]; rejectCustomerTax?: boolean; holdReads?: boolean; readFailure?: number; noPrepare?: boolean } = {}) {
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
  const createdCustomers: SavedCustomer[] = structuredClone(options.customerRecords ?? []);
  globalThis.fetch = async (input, init) => {
    const url = new URL(String(input)), method = init?.method ?? "GET", body = init?.body ? JSON.parse(String(init.body)) : null;
    calls.push({ path: url.pathname, query: url.search, method, body, key: new Headers(init?.headers).get("Idempotency-Key") });
    if (method === "GET" && ["/business/invoices", "/business/customers"].some(path => url.pathname.endsWith(path))) {
      if (options.holdReads) return new Promise<Response>(() => {});
      if (options.readFailure) return Response.json({ code: "synthetic_read_failure" }, { status: options.readFailure });
    }
    if (url.pathname.endsWith("/business/invoices") && method === "GET") return Response.json({ items: record ? [record] : [], total: record ? 1 : 0, page: 1, page_size: 25, stage_counts: { draft: record && !record.operation ? 1 : 0, issued: record?.operation?.state.legal === "ACCEPTED" ? 1 : 0, uncertain: record?.operation?.state.submission === "unknown" ? 1 : 0 }, summaries: [], query_version: "synthetic-version" });
    if (url.pathname.endsWith("/business/customers") && method === "GET") return Response.json({ items: createdCustomers, total: createdCustomers.length, page: 1, page_size: 25 });
    if (url.pathname.includes("/business/customers") && ["POST", "PUT"].includes(method)) {
      if (options.rejectCustomerTax && !/^(?:[0-9]{9}|[0-9]{11})$/.test(body.data.tax_id)) return Response.json({ code: "customer_invalid", context: { field_errors: { tax_id: "tax_id" } } }, { status: 422 });
      if (method === "PUT") { const index = createdCustomers.findIndex(customer => url.pathname.endsWith(`/${customer.id}`)); assert.ok(index >= 0); assert.equal(body.expected_version, createdCustomers[index].version); createdCustomers[index] = { ...createdCustomers[index], data: body.data, version: createdCustomers[index].version + 1 }; return Response.json(createdCustomers[index]); }
      const customer = { ...savedCustomer(), data: body.data }; createdCustomers.push(customer); return Response.json(customer);
    }
    if (url.pathname.endsWith("/business/invoices") && method === "POST") {
      if (!record) { record = savedInvoice(body.data); creates++; }
      if (options.holdCreate) { heldSignal = init?.signal; await new Promise<void>(resolve => { releaseCreate = resolve; }); }
      if (loseCreate) { loseCreate = false; throw new TypeError("synthetic response lost after commit"); }
      return Response.json(record);
    }
    if (url.pathname.endsWith(`/business/invoices/${invoiceId}`) && method === "PUT" && record) { record = { ...record, version: record.version + 1, data: body.data, field_errors: options.checkTaxId ? /^(?:[0-9]{9}|[0-9]{11})$/.test(body.data.customer_input.tax_id) ? {} : { "customer_input.tax_id": "tax_id" } : record.field_errors, amounts: body.data.tax_inclusion === "included" ? null : record.amounts }; return Response.json(record); }
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
  const reopen = async () => { await act(async () => root.unmount()); root = createRoot(host); await render(); };
  return { calls, click, fill, button, act, reopen, customerRecords: () => createdCustomers, advanceAccepted: () => { if (record?.operation) record = { ...record, operation: { ...record.operation, state: { ...record.operation.state, submission: "identified", processing: "FINISHED", legal: "ACCEPTED", xml: "available", pdf: "available" } } }; }, resolveDirectory: async () => { currentContext = { ...context, directoryStatus: "ready" }; await render(); }, release: () => releaseCreate?.(), signal: () => heldSignal, record: () => record, creates: () => creates, prepareEffects: () => prepareEffects, async close() { await act(async () => root.unmount()); host.remove(); globalThis.fetch = previousFetch; setChosenGrant(previousGrant); if (previousMock === undefined) delete process.env.NEXT_PUBLIC_MOCK_AUTH; else process.env.NEXT_PUBLIC_MOCK_AUTH = previousMock; removeSessionStored("cuadrao:invoice_commands:v1"); } };
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
      await page.click(invoiceId); await page.click("Edit draft"); await page.fill("#invoice-taxId", digits);
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
    await page.click(invoiceId); await page.click("Edit draft"); await page.fill("#invoice-customer-search", "Draft customer"); await page.click("Add customer · Draft customer"); await page.fill("#invoice-taxId", "131-79389-1"); await page.click("Save draft");
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
