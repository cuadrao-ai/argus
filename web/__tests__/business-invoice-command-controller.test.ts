import { afterEach, beforeEach, expect, test } from "bun:test";
import { createInvoiceCommandController, type InvoiceCommand, type InvoiceCommandJournal, type InvoiceCommandTransport } from "@/components/business-app/invoicing/invoice-command-controller";
import { InvoiceProblem } from "@/lib/business-invoices-api";
import { getChosenGrant, setChosenGrant } from "@/lib/business-grant";
import { invoiceScope, incompleteInvoice, savedInvoice, savedCustomer } from "./fixtures/business-invoice-fixture";
const originalGrant = getChosenGrant();
beforeEach(() => setChosenGrant(invoiceScope.grantId));
afterEach(() => setChosenGrant(originalGrant));
function journal(): InvoiceCommandJournal {
  let pending: InvoiceCommand | null = null;
  return { read: () => pending ? structuredClone(pending) : null, write: (_, command) => { pending = structuredClone(command); return true; }, clear: () => { pending = null; } };
}
const transport = (): InvoiceCommandTransport => ({ invoice: async (_, __, ___, body) => savedInvoice(body.data), customer: async () => savedCustomer(), prepare: async () => savedInvoice(), submit: async () => savedInvoice() });
const create = (): Extract<InvoiceCommand, { kind: "invoice" }> => ({ kind: "invoice", id: null, key: "one-original-create", body: { data: incompleteInvoice(), expected_version: null } });
test("an incomplete invoice saves without creating a customer or guessing fiscal choices", async () => {
  const store = journal(), wire = transport(); let customers = 0;
  wire.customer = async () => { customers++; return savedCustomer(); };
  const controller = createInvoiceCommandController(invoiceScope, store, wire);
  await controller.submit(create()); const state = controller.getSnapshot();
  expect(state.kind).toBe("saved"); expect(customers).toBe(0); expect(store.read(invoiceScope)).toBeNull();
  if (state.kind === "saved" && state.result.kind === "invoice") { expect(state.result.record.data.payment_type).toBeNull(); expect(state.result.record.outstanding_amount).toBeNull(); }
  controller.dispose();
});
test("lost create response survives reload and retries the same key, payload and target", async () => {
  const store = journal(), wire = transport(), calls: unknown[] = []; let attempts = 0;
  wire.invoice = async (_, id, key, body) => { calls.push({ id, key, body: structuredClone(body) }); if (!attempts++) throw new TypeError("response lost after commit"); return savedInvoice(body.data); };
  const first = createInvoiceCommandController(invoiceScope, store, wire), command = create();
  await first.submit(command); command.body.data.notes = "later edit";
  await first.submit({ ...create(), key: "must-not-create-again" }); expect(calls).toHaveLength(1); first.dispose();
  const reopened = createInvoiceCommandController(invoiceScope, store, wire);
  expect(reopened.getSnapshot().kind).toBe("failed"); await reopened.retry();
  expect(calls).toHaveLength(2); expect(calls[1]).toEqual(calls[0]); expect(reopened.getSnapshot().kind).toBe("saved"); reopened.dispose();
});
test("failed session persistence prevents a create request", async () => {
  const wire = transport(); let sent = false;
  wire.invoice = async () => { sent = true; return savedInvoice(); };
  const controller = createInvoiceCommandController(invoiceScope, { ...journal(), write: () => false }, wire);
  await controller.submit(create()); expect(sent).toBe(false); expect(controller.getSnapshot()).toMatchObject({ kind: "failed", failure: "storage" }); controller.dispose();
});
test("a version conflict preserves the attempted draft for a newly reviewed version", async () => {
  const wire = transport(); let attempts = 0;
  wire.invoice = async (_, __, ___, body) => { if (!attempts++) throw new InvoiceProblem(409, "invoice_stale_version"); return savedInvoice(body.data); };
  const controller = createInvoiceCommandController(invoiceScope, journal(), wire), command = create(); command.body.data.notes = "keep my text";
  await controller.submit(command); expect(controller.getSnapshot()).toMatchObject({ kind: "failed", failure: "conflict", command: { body: { data: { notes: "keep my text" } } } });
  await controller.submit({ ...command, key: "reviewed-version", body: { ...command.body, expected_version: 2 } }); expect(controller.getSnapshot().kind).toBe("saved"); controller.dispose();
});
test("revoked authority clears exposed draft state and never retries automatically", async () => {
  const wire = transport(); let calls = 0;
  wire.invoice = async () => { calls++; throw new InvoiceProblem(403, "business_grant_not_live"); };
  const controller = createInvoiceCommandController(invoiceScope, journal(), wire);
  await controller.submit(create()); await controller.retry(); await controller.submit(create());
  expect(calls).toBe(1); expect(controller.getSnapshot()).toMatchObject({ kind: "failed", command: null, failure: "access" }); controller.dispose();
});
test("a Business switch aborts a save and rejects its late response even after switching back", async () => {
  const wire = transport(); let finish: (() => void) | undefined;
  wire.invoice = async (_, __, ___, body, signal) => { await new Promise<void>(resolve => { finish = resolve; }); expect(signal?.aborted).toBe(true); return savedInvoice(body.data); };
  const controller = createInvoiceCommandController(invoiceScope, journal(), wire), pending = controller.submit(create());
  setChosenGrant(null); setChosenGrant(invoiceScope.grantId); finish?.(); await pending;
  expect(controller.getSnapshot().kind).toBe("disposed");
});

test("retry must persist the same frozen command again before sending", async () => {
  const store = journal(), wire = transport(); let available = true, sent = 0;
  const originalWrite = store.write;
  store.write = (scope, command) => available && originalWrite(scope, command);
  wire.invoice = async () => { sent++; throw new TypeError("response lost"); };
  const controller = createInvoiceCommandController(invoiceScope, store, wire);
  await controller.submit(create()); available = false; await controller.retry();
  expect(sent).toBe(1); expect(controller.getSnapshot()).toMatchObject({ kind: "failed", failure: "storage", retryable: true });
  available = true; await controller.retry(); expect(sent).toBe(2);
  expect(store.read(invoiceScope)).toEqual(create()); controller.dispose();
});

test("an idempotency conflict never discards unresolved intent or permits a new create", async () => {
  const store = journal(), wire = transport(); let sent = 0;
  wire.invoice = async () => { sent++; throw new InvoiceProblem(409, "invoice_idempotency_conflict"); };
  const controller = createInvoiceCommandController(invoiceScope, store, wire);
  await controller.submit(create()); await controller.submit({ ...create(), key: "new-create-must-stay-blocked" });
  expect(sent).toBe(1); expect(store.read(invoiceScope)).toEqual(create());
  expect(controller.getSnapshot()).toMatchObject({ kind: "failed", retryable: true }); controller.dispose();
});

test("invalid command input stays visible as validation failure and sends no request", async () => {
  const wire = transport(); let sent = 0;
  wire.customer = async () => { sent++; return savedCustomer(); };
  const controller = createInvoiceCommandController(invoiceScope, journal(), wire);
  await expect(controller.submit({ kind: "customer", id: null, key: "invalid-tax", body: { data: { ...savedCustomer().data, tax_id: "x".repeat(33) }, archived: false, expected_version: null } })).resolves.toBeUndefined();
  expect(sent).toBe(0); expect(controller.getSnapshot()).toMatchObject({ kind: "failed", failure: "invalid", fieldErrors: { tax_id: "invalid" } }); controller.dispose();
});
