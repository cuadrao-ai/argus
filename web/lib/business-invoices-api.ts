import { z } from "zod";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { ARGUS_API_BASE_URL, argusApiRequestHeaders, serverRequestId } from "./argus-api-transport";
import { getChosenGrant, subscribeChosenGrant } from "./business-grant";

const uuid = z.string().uuid();
const text = (max: number) => z.string().max(max);
export const customerInputSchema = z.strictObject({ name: text(200), email: text(254), tax_id: text(32), address: text(500), phone: text(40), notes: text(500) });
export const customerInputLimits = {
  name: customerInputSchema.shape.name.maxLength ?? undefined,
  email: customerInputSchema.shape.email.maxLength ?? undefined,
  taxId: customerInputSchema.shape.tax_id.maxLength ?? undefined,
  address: customerInputSchema.shape.address.maxLength ?? undefined,
} as const;
const itemSchema = z.strictObject({ id: text(80).min(1), description: text(160), quantity: text(32), price: text(32), tax: text(32), discount: text(32), classification: z.enum(["goods", "services"]).nullable(), tax_treatment: z.enum(["taxable", "exempt"]).nullable() });
export const invoiceDraftSchema = z.strictObject({
  customer_id: uuid.nullable(), customer_input: customerInputSchema,
  document_type: z.enum(["E31", "E32"]), currency: z.enum(["DOP", "USD", "EUR"]), issued_on: text(10), due_on: text(10),
  items: z.array(itemSchema).max(50).refine(items => new Set(items.map(item => item.id)).size === items.length),
  terms: text(500), instructions: text(500), notes: text(500),
  delivery: z.strictObject({ to: text(254), cc: z.array(text(254)).max(5), message: text(500) }),
  payment_type: z.enum(["cash", "credit", "free"]).nullable(), income_type: z.union([z.literal(1), z.literal(2), z.literal(3), z.literal(4), z.literal(5), z.literal(6)]).nullable(), tax_inclusion: z.enum(["excluded", "included"]).nullable(),
});
export const operationSchema = z.object({
  id: uuid, business_id: uuid, invoice_id: uuid.nullable(), invoice_revision_id: uuid.nullable(), case_id: z.string(), kind: z.enum(["E31", "E32"]), number: z.string(), payload_digest: z.string().regex(/^[a-f0-9]{64}$/), provider_id: z.string().nullable(),
  state: z.object({ submission: z.enum(["prepared", "contacted", "unknown", "identified"]), processing: z.enum(["unreported", "REGISTERED", "TO_SEND", "WAITING_RESPONSE", "TO_NOTIFY", "FINISHED"]), legal: z.enum(["unreported", "ACCEPTED", "ACCEPTED_WITH_OBSERVATIONS", "REJECTED"]), xml: z.enum(["unreported", "available", "unavailable", "retrieval_failed"]), pdf: z.enum(["unreported", "available", "unavailable", "retrieval_failed"]), delivery: z.literal("not_requested"), reconciliation: z.enum(["not_needed", "pending", "identity_missing", "exhausted", "conflict"]), diagnostics: z.array(z.string()), needs_review: z.boolean() }),
});
export const customerSchema = z.object({ id: uuid, business_id: uuid, version: z.number().int().positive(), data: customerInputSchema, archived: z.boolean(), created_at: z.string(), updated_at: z.string() });
const amount = z.string().regex(/^\d+\.\d{2}$/);
export const invoiceSchema = z.object({ id: uuid, business_id: uuid, version: z.number().int().positive(), revision_id: uuid, data: invoiceDraftSchema, field_errors: z.record(z.string(), z.string()), amounts: z.object({ subtotal: amount, discount: amount, tax: amount, total: amount }).nullable(), operation: operationSchema.nullable(), payment_state: z.literal("unknown"), paid_amount: z.null(), outstanding_amount: z.null(), delivery_state: z.literal("not_sent"), created_at: z.string(), updated_at: z.string() });
function invoiceIdentity(value: SavedInvoice): SavedInvoice {
  if (value.operation && (value.operation.business_id !== value.business_id || value.operation.invoice_id !== value.id || value.operation.invoice_revision_id !== value.revision_id)) throw new InvoiceScopeChanged();
  return value;
}
const pagination = { total: z.number().int().nonnegative(), page: z.number().int().positive(), page_size: z.union([z.literal(25), z.literal(50), z.literal(100)]) };
const customerPageSchema = z.object({ items: z.array(customerSchema), ...pagination });
const invoicePageSchema = z.object({ items: z.array(invoiceSchema), ...pagination, stage_counts: z.record(z.string(), z.number().int().nonnegative()), summaries: z.array(z.object({ currency: z.enum(["DOP", "USD", "EUR"]), billed: amount, collected: z.null(), outstanding: z.null() })), query_version: z.string(), issuance_available: z.boolean().default(false) });
export type InvoiceDraft = z.infer<typeof invoiceDraftSchema>;
export type SavedInvoice = z.infer<typeof invoiceSchema>;
export type SavedCustomer = z.infer<typeof customerSchema>;
export type CustomerInput = z.infer<typeof customerInputSchema>;
export type FiscalOperation = z.infer<typeof operationSchema>;
export type InvoiceScope = Readonly<{ userId: string; businessId: string; grantId: string | null }>;
export type InvoicePage = z.infer<typeof invoicePageSchema>;
export type CustomerPage = z.infer<typeof customerPageSchema>;
export type InvoiceQuery = { page: number; page_size: 25 | 50 | 100; search: string; stage?: "all" | "draft" | "issued" | "processing" | "rejected" | "uncertain"; currency?: "DOP" | "USD" | "EUR"; date_from?: string; date_to?: string; sort?: "newest" | "oldest" };
export const customerWriteSchema = z.strictObject({ data: customerInputSchema, archived: z.boolean(), expected_version: z.number().int().positive().nullable() });
export const invoiceWriteSchema = z.strictObject({ data: invoiceDraftSchema, expected_version: z.number().int().positive().nullable() });
export type InvoiceWrite = z.infer<typeof invoiceWriteSchema>;
export type CustomerWrite = z.infer<typeof customerWriteSchema>;
export class InvoiceProblem extends Error {
  constructor(readonly status: number, readonly code: string, readonly fieldErrors: Record<string, string> = {}, readonly requestId?: string) { super(code); }
}
export class InvoiceScopeChanged extends Error { constructor() { super("Business invoice scope changed"); } }

async function request<T>(scope: InvoiceScope, path: string, options: RequestInit, consume: (response: Response) => Promise<T>): Promise<T> {
  const generation = browserAuthGeneration(), abort = new AbortController();
  let changed = false;
  const unsubscribe = subscribeChosenGrant(() => { if (getChosenGrant() !== scope.grantId) { changed = true; abort.abort(); } });
  const check = () => { options.signal?.throwIfAborted(); requireBrowserAuthGeneration(generation); if (changed || getChosenGrant() !== scope.grantId) throw new InvoiceScopeChanged(); };
  try {
    check();
    const auth = await authenticatedRequestHeaders(scope.userId);
    check();
    const signals = [abort.signal, AbortSignal.timeout(30_000), ...(options.signal ? [options.signal] : [])];
    const response = await fetch(`${ARGUS_API_BASE_URL}${path}`, { ...options, cache: "no-store", credentials: "omit", signal: AbortSignal.any(signals), headers: argusApiRequestHeaders(options.headers, auth, path) });
    check();
    if (!response.ok) {
      const body = z.record(z.string(), z.unknown()).catch({}).parse(await response.json().catch(() => ({})));
      check();
      const detail = z.record(z.string(), z.unknown()).catch({}).parse(body.detail);
      const context = z.record(z.string(), z.unknown()).catch({}).parse(detail.context ?? body.context);
      throw new InvoiceProblem(response.status, String(detail.code ?? body.code ?? "invoice_request_failed"), z.record(z.string(), z.string()).catch({}).parse(context.field_errors), serverRequestId(response, body));
    }
    const result = await consume(response);
    check();
    return result;
  } finally { unsubscribe(); }
}
function scoped<T extends { business_id: string; id: string }>(scope: InvoiceScope, value: T, expectedId?: string | null): T {
  if (value.business_id !== scope.businessId || expectedId && value.id !== expectedId) throw new InvoiceScopeChanged();
  return value;
}
function operationIdentity(invoice: SavedInvoice, operation: FiscalOperation): FiscalOperation {
  if (!invoice.operation || operation.id !== invoice.operation.id || operation.payload_digest !== invoice.operation.payload_digest || operation.business_id !== invoice.business_id || operation.invoice_id !== invoice.id || operation.invoice_revision_id !== invoice.revision_id) throw new InvoiceScopeChanged();
  return operation;
}
const idPath = (id: string) => encodeURIComponent(uuid.parse(id));
async function json<T>(scope: InvoiceScope, path: string, schema: z.ZodType<T>, options: RequestInit = {}): Promise<T> { return request(scope, path, options, async response => schema.parse(await response.json())); }
const queryString = (query: InvoiceQuery & { archived?: boolean }) => new URLSearchParams(Object.entries(query).filter(([, value]) => value !== undefined).map(([key, value]) => [key, String(value)])).toString();
export async function listInvoices(scope: InvoiceScope, query: InvoiceQuery, signal?: AbortSignal): Promise<InvoicePage> {
  const page = await json(scope, `/business/invoices?${queryString(query)}`, invoicePageSchema, { signal });
  page.items.forEach(item => invoiceIdentity(scoped(scope, item))); return page;
}
export async function listCustomers(scope: InvoiceScope, query: Pick<InvoiceQuery, "page" | "page_size" | "search"> & { archived?: boolean }, signal?: AbortSignal): Promise<CustomerPage> {
  const page = await json(scope, `/business/customers?${queryString(query)}`, customerPageSchema, { signal });
  page.items.forEach(item => scoped(scope, item)); return page;
}
export async function getInvoice(scope: InvoiceScope, id: string, signal?: AbortSignal): Promise<SavedInvoice> { return invoiceIdentity(scoped(scope, await json(scope, `/business/invoices/${idPath(id)}`, invoiceSchema, { signal }), id)); }
export async function saveInvoice(scope: InvoiceScope, id: string | null, key: string, body: InvoiceWrite, signal?: AbortSignal): Promise<SavedInvoice> {
  return invoiceIdentity(scoped(scope, await json(scope, `/business/invoices${id ? `/${idPath(id)}` : ""}`, invoiceSchema, { method: id ? "PUT" : "POST", headers: { "Idempotency-Key": z.string().min(1).max(200).parse(key) }, body: JSON.stringify(invoiceWriteSchema.parse(body)), signal }), id));
}
export async function getCustomer(scope: InvoiceScope, id: string, signal?: AbortSignal): Promise<SavedCustomer> { return scoped(scope, await json(scope, `/business/customers/${idPath(id)}`, customerSchema, { signal }), id); }
export async function saveCustomer(scope: InvoiceScope, id: string | null, key: string, body: CustomerWrite, signal?: AbortSignal): Promise<SavedCustomer> {
  return scoped(scope, await json(scope, `/business/customers${id ? `/${idPath(id)}` : ""}`, customerSchema, { method: id ? "PUT" : "POST", headers: { "Idempotency-Key": z.string().min(1).max(200).parse(key) }, body: JSON.stringify(customerWriteSchema.parse(body)), signal }), id);
}
export async function prepareInvoice(scope: InvoiceScope, id: string, version: number, signal?: AbortSignal): Promise<SavedInvoice> { return invoiceIdentity(scoped(scope, await json(scope, `/business/invoices/${idPath(id)}/prepare`, invoiceSchema, { method: "POST", body: JSON.stringify({ expected_version: z.number().int().positive().parse(version) }), signal }), id)); }
export async function getInvoiceOperation(scope: InvoiceScope, invoice: SavedInvoice, signal?: AbortSignal): Promise<FiscalOperation> {
  if (!invoice.operation) throw new Error("Invoice has no operation");
  const operation = scoped(scope, await json(scope, `/business/fiscal-operations/${idPath(invoice.operation.id)}`, operationSchema, { signal }));
  return operationIdentity(invoice, operation);
}
export async function downloadInvoiceArtifact(scope: InvoiceScope, invoice: SavedInvoice, kind: "xml" | "pdf", signal?: AbortSignal): Promise<Blob> {
  invoiceIdentity(scoped(scope, invoice));
  if (!invoice.operation || invoice.operation.state[kind] !== "available") throw new Error("Invoice artifact unavailable");
  return request(scope, `/business/fiscal-operations/${idPath(invoice.operation.id)}/artifacts/${kind}`, { signal }, async response => {
    if (response.headers.get("Content-Type")?.split(";")[0] !== (kind === "pdf" ? "application/pdf" : "application/xml")) throw new Error("Invalid invoice artifact");
    return response.blob();
  });
}

export async function submitInvoice(scope: InvoiceScope, id: string, operationId: string, payloadDigest: string, signal?: AbortSignal): Promise<SavedInvoice> {
  const invoice = await getInvoice(scope, id, signal);
  if (invoice.operation?.id !== operationId || invoice.operation.payload_digest !== payloadDigest) throw new InvoiceScopeChanged();
  const current = await getInvoiceOperation(scope, invoice, signal);
  if (current.state.submission !== "prepared") return { ...invoice, operation: current };
  const operation = scoped(scope, await json(scope, `/business/fiscal-operations/${idPath(operationId)}/submit`, operationSchema, { method: "POST", body: JSON.stringify({ payload_digest: z.string().regex(/^[a-f0-9]{64}$/).parse(payloadDigest) }), signal }));
  return invoiceIdentity({ ...invoice, operation: operationIdentity(invoice, operation) });
}
