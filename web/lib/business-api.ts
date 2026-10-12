import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake } from "./business-email";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { apiFetch, ARGUS_API_BASE_URL, argusApiRequestHeaders } from "./argus-api-transport";
import type { ArgusLanguage } from "./language-features";
import type { BusinessDossier, BusinessFactPatch, BusinessRecordContext } from "./business-dossier";

/**
 * The Business pilot's view of `/api/v1/business`. The backend owns every
 * fact here: statuses, totals, review fields and links. The web renders them.
 */

export type CurrencyCode = string;
export type DecimalString = string;

export type ReceiptStatus =
  | "saved"
  | "queued"
  | "preparing"
  | "review_ready"
  | "needs_attention"
  | "confirmed"
  | "dismissed";

export type ReceiptChannel = "web" | "whatsapp";

/** Why a `needs_attention` receipt needs the owner. The backend decides it. */
export const RECEIPT_ATTENTIONS = [
  "unreadable",
  "ai_unavailable",
  "interrupted",
  "outcome_unknown",
  "no_purchase_found",
  "several_purchases",
  "source_unavailable",
  "check_details",
  "duplicate",
  "other",
] as const;
export type ReceiptAttention = (typeof RECEIPT_ATTENTIONS)[number];

export type ReceiptReviewFields = {
  merchant: string | null;
  occurred_on: string | null;
  amount: DecimalString | null;
  currency: CurrencyCode | null;
  category_id: string | null;
  account_id: string | null;
};

export type ReceiptSummary = ReceiptReviewFields & {
  id: string;
  channel: ReceiptChannel;
  filename: string | null;
  /** The sender's own words sent with the file (a WhatsApp caption), verbatim. */
  source_text?: string | null;
  media_type: string;
  size_bytes: number;
  received_at: string;
  status: ReceiptStatus;
  error_code: string | null;
  attention: ReceiptAttention | null;
  /** With attention `duplicate`: the receipt this one may repeat. */
  duplicate_of?: string | null;
  /** The upload found the same bytes already saved; this is that receipt. */
  replayed?: boolean;
  /** The owner may ask for a consented AI read now. */
  preparable: boolean;
  /** The owner may fill in the one purchase by hand from version 0. */
  enterable: boolean;
  /** Email deliveries this document arrived in, if any. */
  email_delivery_ids?: string[];
  /** The email itself, whose attachment is already a receipt; never prepared or approved. */
  email_original?: boolean;
  expense_id: string | null;
};

export type ReceiptEvidenceLine = {
  description: string;
  amount: DecimalString | null;
};

export type ReceiptDetail = ReceiptSummary & BusinessRecordContext & {
  draft_id: string | null;
  version: number;
  evidence: {
    merchant: string | null;
    occurred_on: string | null;
    total: DecimalString | null;
    currency: CurrencyCode | null;
    tax: DecimalString | null;
    tip: DecimalString | null;
    service: DecimalString | null;
    lines: ReceiptEvidenceLine[];
  } | null;
  missing_fields: (keyof ReceiptReviewFields)[];
};

export function businessExportPeriodValid(start: string, end: string): boolean {
  const date = (value: string) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value) || value.startsWith("0000-")) return NaN;
    const parsed = Date.parse(`${value}T00:00:00Z`);
    return Number.isFinite(parsed) && new Date(parsed).toISOString().slice(0, 10) === value ? parsed : NaN;
  };
  const days = (date(end) - date(start)) / 86_400_000;
  return days >= 0 && days <= 365;
}

export async function fetchBusinessExport(draftId: string, start: string, end: string, signal?: AbortSignal): Promise<Blob> {
  const authHeaders = await authenticatedRequestHeaders();
  signal?.throwIfAborted();
  const query = new URLSearchParams({ start, end, draft_id: draftId });
  const response = await fetch(`${ARGUS_API_BASE_URL}/business/exports?${query}`, {
    headers: authHeaders, credentials: "include", cache: "no-store", signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error("Business export unavailable") as Error & { status: number; code: string };
    error.status = response.status;
    error.code = body?.detail?.code ?? body?.code ?? "unknown";
    throw error;
  }
  if (response.headers.get("Content-Type")?.split(";")[0].trim() !== "application/zip") throw new Error("Invalid Business export response");
  return response.blob();
}

export async function getBusinessDossier(draftId: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/dossier`);
}

export async function reviewBusinessDraft(draftId: string, version: number, facts: BusinessFactPatch, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/review`, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, facts }),
  });
}

export async function approveBusinessDraft(draftId: string, version: number, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/approve`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, action: "record_expense" }),
  });
}

export async function settleBusinessRemainder(draftId: string, version: number, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/remainder/settle`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version }),
  });
}

export type BusinessAccount = {
  id: string;
  nickname: string | null;
  type: string;
  currency: CurrencyCode;
};

export type BusinessWorkspaceInfo = {
  accounts: BusinessAccount[];
  currencies: CurrencyCode[];
  /** Whether Business conversations can answer questions about saved expenses. */
  assistant_available: boolean;
  /** Whether Business conversations can be started or continued at all. */
  chat_available: boolean;
  /** What a receipt upload accepts. The backend's document settings own it. */
  receipt_limits: ReceiptLimits;
};

/**
 * The one reader of `chat_available`. Closed until the backend says so, so a
 * workspace still loading, or an older payload without the field, offers no chat.
 */
export function businessChatAvailable(workspace: BusinessWorkspaceInfo | null): boolean {
  return workspace?.chat_available === true;
}

export type ReceiptLimits = {
  max_bytes: number;
  media_types: string[];
};

export type BusinessExpense = {
  id: string;
  merchant: string | null;
  amount: DecimalString;
  currency: CurrencyCode;
  category_id: string | null;
  account_id: string | null;
  funding?: "owner_funds";
  occurred_on: string;
  receipt_id: string | null;
};

export type BusinessOverview = {
  from: string;
  to: string;
  /** The server's day in the Business time zone: the one clock for "today". */
  today: string;
  totals: { currency: CurrencyCode; amount: DecimalString; count: number }[];
  needs_attention: number;
  last_received_at: string | null;
  last_confirmed_at: string | null;
  /** Saved expenses the chosen period leaves out, so none looks vanished. */
  outside_period_count: number;
  outside_period_latest_on: string | null;
};

export type BusinessUpdate = {
  id: string;
  kind: "receipt_ready" | "receipt_needs_attention" | "expense_confirmed";
  occurred_at: string;
  receipt_id: string | null;
  expense_id: string | null;
  error_code: string | null;
  attention: ReceiptAttention | null;
  label: string | null;
};

/**
 * Business records matching a query, each list capped by `limit`. A receipt
 * whose expense also matched is only under its expense, as `receipt_id`.
 */
export type BusinessSearchResult = {
  expenses: BusinessExpense[];
  receipts: ReceiptSummary[];
  accounts: BusinessAccount[];
};

export type BusinessCaptureInput = { text: string; draft?: { draft_id: string; version: number } };
export type BusinessCapture = {
  draft_id: string;
  version: number;
  source_id: string;
  text: string;
  received_at: string;
  review_state: BusinessDossier["review_state"];
};

export async function captureBusinessNote(input: BusinessCaptureInput, key: string): Promise<BusinessDossier> {
  const authHeaders = await authenticatedRequestHeaders();
  const response = await fetch(`${ARGUS_API_BASE_URL}/business/captures`, {
    method: "POST",
    credentials: "include",
    headers: argusApiRequestHeaders({ "Idempotency-Key": key }, authHeaders),
    body: JSON.stringify(input),
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({})) as { code?: unknown; detail?: unknown };
    const problem = typeof body.detail === "object" && body.detail !== null ? body.detail as { code?: unknown } : body;
    const code = typeof problem.code === "string" ? problem.code : "unknown";
    throw Object.assign(new Error("Capture request could not be confirmed"), { status: response.status, code });
  }
  return response.json() as Promise<BusinessDossier>;
}

export async function listBusinessCaptures(query = "", limit = 20): Promise<BusinessCapture[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit) });
  const page = await apiFetch<{ items: BusinessCapture[] }>(`/business/captures?${params}`);
  return page.items;
}

export type ExpenseInput = {
  account_id: string;
  amount: DecimalString;
  occurred_on: string;
  merchant: string | null;
  category_id: string | null;
};

/** The owner's one Business space. Business records live only inside it. */
export type BusinessSpace = { id: string; name: string };

/**
 * Starts the owner's Business space, or returns the one they already have.
 * Every other Business route answers 404 until it exists. The server names a
 * new space in `language`.
 */
export async function startBusinessSpace(language: ArgusLanguage): Promise<BusinessSpace> {
  return apiFetch("/business/space", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
}

export async function getBusinessWorkspace(): Promise<BusinessWorkspaceInfo> {
  return apiFetch("/business/workspace");
}

export async function getBusinessOverview(
  from: string,
  to: string | null,
): Promise<BusinessOverview> {
  const query = new URLSearchParams(to === null ? { from } : { from, to });
  return apiFetch(`/business/overview?${query}`);
}

export async function listBusinessReceipts(
  view: "inbox" | "all",
): Promise<ReceiptSummary[]> {
  const page = await apiFetch<{ items: ReceiptSummary[] }>(
    `/business/receipts?view=${view}`,
  );
  return page.items;
}

export async function getBusinessReceipt(id: string): Promise<ReceiptDetail> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}`);
}

export async function listBusinessUpdates(): Promise<BusinessUpdate[]> {
  const page = await apiFetch<{ items: BusinessUpdate[] }>("/business/updates");
  return page.items;
}

export async function searchBusiness(q: string, limit = 5): Promise<BusinessSearchResult> {
  const query = new URLSearchParams({ q, limit: String(limit) });
  return apiFetch(`/business/search?${query}`);
}

export async function listBusinessExpenses(
  from: string,
  to: string | null,
): Promise<BusinessExpense[]> {
  const query = new URLSearchParams(to === null ? { from } : { from, to });
  const page = await apiFetch<{ items: BusinessExpense[] }>(
    `/business/expenses?${query}`,
  );
  return page.items;
}

export async function uploadBusinessReceipt(
  file: File,
  consentToPrepare: boolean,
  idempotencyKey: string,
): Promise<ReceiptSummary> {
  const authHeaders = await authenticatedRequestHeaders();
  const headers = argusApiRequestHeaders(
    {
      "Content-Type": file.type,
      "Idempotency-Key": idempotencyKey,
      "X-Document-Filename": encodeURIComponent(file.name),
      ...(consentToPrepare ? { "X-Extraction-Consent": "true" } : {}),
    },
    authHeaders,
  );
  const response = await fetch(`${ARGUS_API_BASE_URL}/business/receipts`, {
    method: "POST",
    body: file,
    credentials: "include",
    headers,
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: string };
    const error = new Error(body.code ?? `API error ${response.status}`) as Error & {
      status: number;
      code: string;
    };
    error.status = response.status;
    error.code = body.code ?? "unknown";
    throw error;
  }
  return response.json() as Promise<ReceiptSummary>;
}

export async function fetchBusinessReceiptSource(id: string): Promise<Blob> {
  const authHeaders = await authenticatedRequestHeaders();
  const response = await fetch(
    `${ARGUS_API_BASE_URL}/business/receipts/${encodeURIComponent(id)}/source`,
    { credentials: "include", headers: authHeaders },
  );
  if (!response.ok) throw new Error(`API error ${response.status}`);
  return response.blob();
}

export async function prepareBusinessReceipt(id: string): Promise<ReceiptSummary> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}/prepare`, {
    method: "POST",
    headers: { "X-Extraction-Consent": "true" },
  });
}

export async function saveBusinessReceiptReview(
  id: string,
  version: number,
  fields: Partial<ReceiptReviewFields>,
): Promise<ReceiptDetail> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}/review`, {
    method: "PATCH",
    body: JSON.stringify({ version, fields }),
  });
}

export async function confirmBusinessReceipt(
  id: string,
  version: number,
  idempotencyKey: string,
): Promise<ReceiptDetail> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}/confirm`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version }),
  });
}

export async function recordBusinessExpense(
  input: ExpenseInput,
  idempotencyKey: string,
): Promise<BusinessExpense> {
  return apiFetch("/business/expenses", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  });
}

export async function createBusinessAccount(
  input: { nickname: string; type: string; currency: CurrencyCode },
  idempotencyKey: string,
): Promise<BusinessAccount> {
  return apiFetch("/business/accounts", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify(input),
  });
}

export async function getBusinessEmailIntake(): Promise<BusinessEmailIntake> {
  return apiFetch("/business/email");
}

export async function createBusinessEmailAddress(): Promise<BusinessEmailIntake> {
  return apiFetch("/business/email", { method: "POST" });
}

export async function listBusinessEmailDeliveries(): Promise<BusinessEmailDelivery[]> {
  const page = await apiFetch<{ items: BusinessEmailDelivery[] }>("/business/email/deliveries");
  return page.items;
}

export async function getBusinessEmailDelivery(id: string): Promise<BusinessEmailDetail> {
  return apiFetch(`/business/email/deliveries/${encodeURIComponent(id)}`);
}

export async function retryBusinessEmailDelivery(id: string): Promise<{ id: string }> {
  return apiFetch(`/business/email/deliveries/${encodeURIComponent(id)}/retry`, { method: "POST" });
}

/** Who may act in the owner's Business. The grant is the only authority. */
export type BusinessAccessCapability = "read" | "prepare" | "approve";
export type BusinessAccessGrant = {
  id: string;
  email: string | null;
  display_name: string;
  capabilities: BusinessAccessCapability[];
  created_at: string;
  owner: boolean;
};
export type BusinessAccessInvite = { id: string; email: string; created_at: string; expires_at: string };
export type BusinessAccess = { grants: BusinessAccessGrant[]; invites: BusinessAccessInvite[] };

export async function getBusinessAccess(): Promise<BusinessAccess> {
  return apiFetch("/business/access");
}

/** A read and prepare grant for a confirmed account, else a pending invite; the server answers with the whole list either way. */
export async function giveBusinessAccess(email: string): Promise<BusinessAccess> {
  return apiFetch("/business/access", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ email }),
  });
}

export async function revokeBusinessAccessGrant(id: string): Promise<void> {
  await apiFetch(`/business/access/grants/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function revokeBusinessAccessInvite(id: string): Promise<void> {
  await apiFetch(`/business/access/invites/${encodeURIComponent(id)}`, { method: "DELETE" });
}

/** Owner action: bind a receipt whose preparation grant is no longer live to the owner's current grant. */
export async function rebindBusinessReceipt(id: string): Promise<ReceiptDetail> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}/rebind`, { method: "POST" });
}
