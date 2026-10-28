import { z } from "zod";
import * as api from "@/lib/business-invoices-api";
import { getChosenGrant, subscribeChosenGrant } from "@/lib/business-grant";
import { browserAuthGeneration } from "@/lib/browser-auth-generation";
import { readSessionStored, removeSessionStored, writeSessionStored } from "@/lib/browser-storage";

const identity = z.object({ userId: z.string().min(1), businessId: z.string().uuid(), grantId: z.string().uuid().nullable() });
const commandId = { id: z.string().uuid().nullable(), key: z.string().min(1).max(200) };
export const invoiceCommandSchema = z.discriminatedUnion("kind", [
  z.strictObject({ kind: z.literal("invoice"), ...commandId, body: api.invoiceWriteSchema }),
  z.strictObject({ kind: z.literal("customer"), ...commandId, body: api.customerWriteSchema }),
  z.strictObject({ kind: z.literal("submit"), id: z.string().uuid(), operation_id: z.string().uuid(), payload_digest: z.string().regex(/^[a-f0-9]{64}$/) }),
  z.strictObject({ kind: z.literal("prepare"), id: z.string().uuid(), expected_version: z.number().int().positive() }),
]);
export type InvoiceCommand = z.infer<typeof invoiceCommandSchema>;
export type CommandResult = { kind: "invoice"; record: api.SavedInvoice } | { kind: "customer"; record: api.SavedCustomer };
export type CommandFailure = "uncertain" | "conflict" | "invalid" | "access" | "storage" | "unavailable" | "refused";
export type CommandState =
  | { kind: "idle" }
  | { kind: "pending"; command: InvoiceCommand }
  | { kind: "failed"; command: InvoiceCommand | null; failure: CommandFailure; fieldErrors: Record<string, string>; retryable: boolean; reference?: string }
  | { kind: "saved"; result: CommandResult }
  | { kind: "disposed" };
export type InvoiceCommandJournal = { read: (scope: api.InvoiceScope) => InvoiceCommand | null; write: (scope: api.InvoiceScope, command: InvoiceCommand) => boolean; clear: (scope: api.InvoiceScope) => void };
const envelope = z.array(z.strictObject({ scope: identity, command: invoiceCommandSchema }));
const STORAGE_KEY = "cuadrao:invoice_commands:v1";
const sameScope = (a: api.InvoiceScope, b: api.InvoiceScope) => a.userId === b.userId && a.businessId === b.businessId && a.grantId === b.grantId;
const entries = () => envelope.parse(JSON.parse(readSessionStored(STORAGE_KEY) ?? "[]"));
export const sessionInvoiceJournal: InvoiceCommandJournal = {
  read: scope => entries().find(entry => sameScope(entry.scope, scope))?.command ?? null,
  write: (scope, command) => {
    try { return writeSessionStored(STORAGE_KEY, JSON.stringify([...entries().filter(entry => !sameScope(entry.scope, scope)), { scope: { userId: scope.userId, businessId: scope.businessId, grantId: scope.grantId }, command }])); }
    catch { return false; }
  },
  clear: scope => {
    const remaining = entries().filter(entry => !sameScope(entry.scope, scope));
    if (remaining.length) writeSessionStored(STORAGE_KEY, JSON.stringify(remaining));
    else removeSessionStored(STORAGE_KEY);
  },
};
const MAYBE_APPLIED_CLIENT_STATUSES = new Set([408, 409, 425, 429]);
function failureOf(error: unknown, command: InvoiceCommand): CommandFailure {
  if (error instanceof api.InvoiceScopeChanged) return "access";
  const status = error instanceof api.InvoiceProblem ? error.status : 0;
  if (status === 401 || status === 403) return "access";
  if (status === 409 && error instanceof api.InvoiceProblem && error.code !== "invoice_idempotency_conflict") return "conflict";
  if (status === 422) return "invalid";
  const fiscalCommand = command.kind === "prepare" || command.kind === "submit";
  if (status === 404 && fiscalCommand && error instanceof api.InvoiceProblem && (error.code === "http_error" || error.code === "fiscal_sandbox_unavailable")) return "unavailable";
  if (status >= 400 && status < 500 && !MAYBE_APPLIED_CLIENT_STATUSES.has(status)) return "refused";
  return "uncertain";
}
export type InvoiceCommandTransport = { invoice: typeof api.saveInvoice; customer: typeof api.saveCustomer; prepare: typeof api.prepareInvoice; submit: typeof api.submitInvoice };
const live: InvoiceCommandTransport = { invoice: api.saveInvoice, customer: api.saveCustomer, prepare: api.prepareInvoice, submit: api.submitInvoice };

export function createInvoiceCommandController(scope: api.InvoiceScope, journal: InvoiceCommandJournal = sessionInvoiceJournal, transport: InvoiceCommandTransport = live) {
  let state: CommandState = { kind: "idle" };
  try {
    const command = journal.read(scope);
    if (command) state = { kind: "failed", command, failure: "uncertain", retryable: true, fieldErrors: {} };
  } catch { state = { kind: "failed", command: null, failure: "storage", retryable: false, fieldErrors: {} }; }
  const listeners = new Set<() => void>(), abort = new AbortController(), generation = browserAuthGeneration();
  let invalidated = false;
  const publish = (next: CommandState) => { state = next; listeners.forEach(listener => listener()); };
  const dispose = () => { invalidated = true; abort.abort(); unsubscribe(); publish({ kind: "disposed" }); };
  const unsubscribe = subscribeChosenGrant(() => { if (getChosenGrant() !== scope.grantId) dispose(); });
  const active = () => !invalidated && getChosenGrant() === scope.grantId && browserAuthGeneration() === generation;
  async function execute(command: InvoiceCommand): Promise<void> {
    if (!active()) { dispose(); return; }
    publish({ kind: "pending", command });
    try {
      const result: CommandResult = command.kind === "customer"
        ? { kind: "customer", record: await transport.customer(scope, command.id, command.key, command.body, abort.signal) }
        : { kind: "invoice", record: command.kind === "invoice" ? await transport.invoice(scope, command.id, command.key, command.body, abort.signal) : command.kind === "prepare" ? await transport.prepare(scope, command.id, command.expected_version, abort.signal) : await transport.submit(scope, command.id, command.operation_id, command.payload_digest, abort.signal) };
      if (!active()) { dispose(); return; }
      if (result.record.business_id !== scope.businessId) { dispose(); return; }
      journal.clear(scope);
      publish({ kind: "saved", result });
    } catch (error) {
      if (!active()) { dispose(); return; }
      const failure = failureOf(error, command);
      const retryable = failure === "uncertain";
      if (!retryable) journal.clear(scope);
      publish({ kind: "failed", command: failure === "access" ? null : command, failure, retryable, fieldErrors: error instanceof api.InvoiceProblem ? error.fieldErrors : {}, reference: error instanceof api.InvoiceProblem ? error.requestId : undefined });
    }
  }
  return {
    getSnapshot: () => state,
    subscribe: (listener: () => void) => { listeners.add(listener); return () => listeners.delete(listener); },
    dispose,
    submit: async (input: InvoiceCommand) => {
      if (!active() || state.kind === "pending" || state.kind === "failed" && (state.retryable || state.failure === "storage" || state.failure === "access")) return;
      const parsed = invoiceCommandSchema.safeParse(input);
      if (!parsed.success) {
        const fieldErrors = Object.fromEntries(parsed.error.issues.map(issue => [issue.path.slice(2).join("."), "invalid"]));
        publish({ kind: "failed", command: null, failure: "invalid", retryable: false, fieldErrors });
        return;
      }
      const command = structuredClone(parsed.data);
      if (!journal.write(scope, command)) { publish({ kind: "failed", command, failure: "storage", retryable: true, fieldErrors: {} }); return; }
      await execute(command);
    },
    retry: async () => {
      if (state.kind !== "failed" || !state.retryable || !state.command) return;
      const command = state.command;
      if (!journal.write(scope, command)) { publish({ kind: "failed", command, failure: "storage", retryable: true, fieldErrors: {} }); return; }
      await execute(command);
    },
  };
}
export type InvoiceCommandController = ReturnType<typeof createInvoiceCommandController>;
