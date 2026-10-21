import type { BusinessEmailDelivery, BusinessEmailDetail, BusinessEmailIntake } from "./business-email";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { apiFetch, ARGUS_API_BASE_URL, argusApiRequestHeaders } from "./argus-api-transport";
import type { ArgusLanguage } from "./language-features";
import type { BusinessDossier, BusinessFactPatch, BusinessRecordContext } from "./business-dossier";
import { getChosenGrant } from "./business-grant";

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

export type ReceiptChannel = "web" | "whatsapp" | "email";

/** Why a `needs_attention` receipt needs the owner. The backend decides it. */
export const RECEIPT_ATTENTIONS = [
  "unreadable",
  "ai_unavailable",
  "interrupted",
  "outcome_unknown",
  "no_purchase_found",
  "not_a_receipt",
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

export type ReceiptActivity = {
  state: "saved_unread" | "reading" | "ready" | "read_failed" | "blocked" | "inactive";
  unread: boolean;
  completion_cursor: string | null;
};
/**
 * The Bandeja's counts, from the server only. `unread_count` is new activity
 * this person has not opened; `pending_review_count` is every row the Bandeja
 * lists (receipts not yet saved or dismissed, and notes no receipt carries);
 * `needs_attention_count` is how many of those receipts need attention.
 */
export type ReceiptActivityCounts = {
  reading_count: number;
  unread_count: number;
  presentation: "working" | "unread" | "none";
  pending_review_count: number;
  needs_attention_count: number;
  /** Rows a person can review now: the Bandeja's Por revisar. */
  ready_to_review_count: number;
  /** Transacciones' Por igualar over every period. Null while bank matching is off, which is not 0. Absent in older payloads. */
  por_igualar_count?: number | null;
};
export type ReceiptReading = { scope_version: number; enabled: boolean; available: boolean; can_change: boolean; disclosure: string; disclosure_token: string | null; route: { gateway: string; interpretation: { model: string }[]; reply: unknown[] } | null; consented_at: string | null; revoked_at: string | null };

export function getReceiptActivity(signal?: AbortSignal): Promise<ReceiptActivityCounts> {
  return apiFetch("/business/receipt-activity", { signal });
}
export function getReceiptReading(language: ArgusLanguage, signal?: AbortSignal): Promise<ReceiptReading> {
  return apiFetch(`/business/receipt-reading?language=${encodeURIComponent(language)}`, { signal });
}
export function setReceiptReading(reading: ReceiptReading, enabled: boolean, language: ArgusLanguage, signal?: AbortSignal): Promise<ReceiptReading> {
  return apiFetch("/business/receipt-reading", { method: "POST", signal, headers: { "Idempotency-Key": crypto.randomUUID() }, body: JSON.stringify({ enabled, scope_version: reading.scope_version, disclosure_token: reading.disclosure_token, language }) });
}
export function markReceiptRead(id: string, completionCursor: string): Promise<ReceiptActivity> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}/read`, { method: "POST", body: JSON.stringify({ completion_cursor: completionCursor }) });
}

export type ReceiptSummary = ReceiptReviewFields & {
  id: string;
  activity?: ReceiptActivity | null;
  channel: ReceiptChannel;
  /** Marked by a person as no part of the Business: left out of the totals, kept visible. */
  personal?: boolean;
  /** Who marked it, when that was someone other than the owner; absent otherwise. */
  personal_marked_by?: string | null;
  /** The server says the receipt's facts exist (a draft owns it), so an empty fiscal_value means no fiscal number; absent before a read. */
  fiscal_known?: boolean;
  /** The fiscal number the draft carries (NCF or e-CF); absent without one or before a read. */
  fiscal_value?: "ncf" | "ecf" | null;
  /** A person stated it has no comprobante fiscal and it carries no NCF or e-CF: it counts in the totals, stays out of the 606 and 607. Absent when false. */
  sin_comprobante?: boolean;
  /** The accountant's 606 answer for a personal receipt with a fiscal number; absent until given. */
  include_606?: boolean | null;
  /** Who gave the 606 answer; absent while there is none. */
  include_606_by?: string | null;
  /** The caller may mark or unmark it: anyone holding prepare, on a receipt that has a draft. */
  personal_editable?: boolean;
  /** `venta` is an invoice this business already issued. Absent means a receipt. */
  document_type?: "recibo" | "venta";
  /** The type was read from the document (its RNC is the Business's own), not picked; absent when false. */
  document_type_detected?: boolean;
  /** True while the draft is open and the caller can prepare: the type can still change. */
  document_type_editable?: boolean;
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
  /** A read is in flight or will start; a queued receipt nothing will read says false and reads as saved. */
  read_pending?: boolean;
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

export type ReceiptDetail = ReceiptSummary & {
  /** The Business this receipt belongs to and what the caller may do there; null when the API cannot say. */
  record_context: BusinessRecordContext | null;
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

export async function fetchBusinessExport(draftId: string | undefined, start: string, end: string, signal?: AbortSignal, expectedGrant = getChosenGrant()): Promise<Blob> {
  const generation = browserAuthGeneration();
  const grant = expectedGrant;
  const requireScope = () => {
    signal?.throwIfAborted();
    requireBrowserAuthGeneration(generation);
    if (getChosenGrant() !== grant) throw new Error("Business selection changed");
  };
  const authHeaders = await authenticatedRequestHeaders();
  requireScope();
  const query = new URLSearchParams({ start, end });
  if (draftId) query.set("draft_id", draftId);
  const response = await fetch(`${ARGUS_API_BASE_URL}/business/exports?${query}`, {
    headers: argusApiRequestHeaders(undefined, authHeaders), credentials: "include", cache: "no-store", signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    const error = new Error("Business export unavailable") as Error & { status: number; code: string };
    error.status = response.status;
    error.code = body?.detail?.code ?? body?.code ?? "unknown";
    throw error;
  }
  if (response.headers.get("Content-Type")?.split(";")[0].trim() !== "application/zip") throw new Error("Invalid Business export response");
  const blob = await response.blob();
  requireScope();
  return blob;
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

/** Compra or Venta on an open draft. Null clears a picked type so the server detects it again. */
export async function setBusinessDraftDocumentType(draftId: string, version: number, documentType: "recibo" | "venta" | null, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/review`, {
    method: "PATCH",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, document_type: documentType }),
  });
}

export async function approveBusinessDraft(draftId: string, version: number, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/approve`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, action: "record_expense" }),
  });
}

/** The draft an approval refused as a second copy of: `duplicate_comprobante` names it in `context.existing_record_id`. */
export function duplicateRecordId(error: unknown): string | null {
  const { code, context } = (error ?? {}) as { code?: unknown; context?: { existing_record_id?: unknown } | null };
  const id = context?.existing_record_id;
  return code === "duplicate_comprobante" && typeof id === "string" && id ? id : null;
}

/** The owner or a prepare-holder marks a receipt as personal (no part of it is the Business's) or takes the mark back. */
export async function markBusinessPersonal(draftId: string, version: number, personal: boolean, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/personal`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, personal }),
  });
}

/** The accountant answers whether a personal receipt with a fiscal number goes into the 606. */
export async function decideBusinessFiscalInclusion(draftId: string, version: number, include: boolean, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/fiscal-inclusion`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version, include }),
  });
}

export async function settleBusinessRemainder(draftId: string, version: number, idempotencyKey: string): Promise<BusinessDossier> {
  return apiFetch(`/business/drafts/${encodeURIComponent(draftId)}/remainder/settle`, {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ version }),
  });
}

/** The account types POST /business/accounts accepts; the server's ExpenseAccountType. */
export const EXPENSE_ACCOUNT_TYPES = ["cash", "checking", "savings", "credit_card"] as const;
export type ExpenseAccountType = (typeof EXPENSE_ACCOUNT_TYPES)[number];


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
  /** The bridge draft that recorded it, when one did: the record to open when no single receipt is named. Absent for a hand-entered expense. */
  draft_id?: string | null;
  /** Marked by a person as no part of the Business: left out of the totals, kept visible. */
  personal?: boolean;
  /** Who marked it, when that was someone other than the owner; absent otherwise. */
  personal_marked_by?: string | null;
  /** The server settles a saved expense's fiscal standing: the number it carries, or none. */
  fiscal_known?: boolean;
  /** The fiscal number the draft carries (NCF or e-CF); absent without one. */
  fiscal_value?: "ncf" | "ecf" | null;
  /** A person stated it has no comprobante fiscal and it carries no NCF or e-CF: it counts in the totals, stays out of the 606 and 607. Absent when false. */
  sin_comprobante?: boolean;
  /** The accountant's 606 answer for a personal expense with a fiscal number; absent until given. */
  include_606?: boolean | null;
  /** Who gave the 606 answer; absent while there is none. */
  include_606_by?: string | null;
};

/** One saved expense with when it was recorded and its revision; both null when the money read does not say. */
export type BusinessExpenseDetail = BusinessExpense & { recorded_at: string | null; revision: number | null };

export type BusinessOverview = {
  from: string;
  to: string;
  /** The server's day in the Business time zone: the one clock for "today". */
  today: string;
  /** "Gastos reales": every approved expense of the period that is not personal. */
  totals: { currency: CurrencyCode; amount: DecimalString; count: number }[];
  /** "Con valor fiscal": those that carry an NCF or an e-CF. Absent in older payloads. */
  fiscal_totals?: { currency: CurrencyCode; amount: DecimalString; count: number }[];
  /** "Sin comprobante fiscal": real minus fiscal, per currency; what does not go into the 606. */
  without_fiscal_totals?: { currency: CurrencyCode; amount: DecimalString; count: number }[];
  last_received_at: string | null;
  last_confirmed_at: string | null;
  /** Saved expenses the chosen period leaves out, so none looks vanished. */
  outside_period_count: number;
  outside_period_latest_on: string | null;
};

/** `document_type` only on a new note: a note on a draft is refused with it. Left out, the note is a detected receipt. */
export type BusinessCaptureInput = { text: string; draft?: { draft_id: string; version: number }; document_type?: "recibo" | "venta" };
export type BusinessCapture = {
  draft_id: string;
  /** The draft's current version, which also counts approvals and settlements. */
  version: number;
  /** The revision this note created: the number the draft's history lists, the one a person sees. */
  revision: number;
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

/** `inbox` asks for the notes the Bandeja lists: drafts awaiting review that no receipt carries. */
export async function listBusinessCaptures(query = "", limit = 20, view: "inbox" | "all" = "all"): Promise<BusinessCapture[]> {
  const params = new URLSearchParams({ q: query, limit: String(limit), view });
  const page = await apiFetch<{ items: BusinessCapture[] }>(`/business/captures?${params}`);
  return page.items;
}


/** The owner's one Business space. Business records live only inside it. */
export type BusinessSpace = { id: string; name: string };

/**
 * Reads the owner's Business space and creates it only when the server
 * confirms it is missing. The server names a new space in `language`.
 */
export async function startBusinessSpace(language: ArgusLanguage): Promise<BusinessSpace> {
  const generation = browserAuthGeneration();
  try {
    return await apiFetch<BusinessSpace>("/business/space");
  } catch (error) {
    const problem = error as { status?: number; code?: string } | null;
    if (problem?.status !== 404 || problem.code !== "business_space_missing") throw error;
  }
  requireBrowserAuthGeneration(generation);
  return apiFetch("/business/space", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ language }),
  });
}

/** One Business the person may enter, through one live grant of theirs; the server's answer, names included. */
export type GrantedSpace = {
  space_id: string;
  name: string;
  grant_id: string;
  role: "owner" | "accountant";
  capabilities: ("read" | "prepare" | "approve")[];
  /** Whether the one-time "you now have access" line was dismissed; always true for the own Business. */
  access_seen: boolean;
};

/** Every Business the person may enter, their own first. */
export async function getBusinessSpaces(): Promise<GrantedSpace[]> {
  const answer = await apiFetch<{ spaces: GrantedSpace[] }>("/business/spaces");
  return answer.spaces;
}

/** The person dismissed the one-time access line for one of their grants; remembered server side. */
export async function markBusinessAccessSeen(grantId: string): Promise<void> {
  const authHeaders = await authenticatedRequestHeaders();
  const response = await fetch(`${ARGUS_API_BASE_URL}/business/spaces/${encodeURIComponent(grantId)}/seen`, {
    method: "POST",
    credentials: "include",
    headers: argusApiRequestHeaders(undefined, authHeaders),
  });
  if (!response.ok) throw new Error(`API error ${response.status}`);
}

/** The person's acceptance of one wording of the consent screen, kept server side; null until accepted. */
export type BusinessConsent = { version: string; accepted_at: string | null };

export function getBusinessConsent(version: string): Promise<BusinessConsent> {
  return apiFetch(`/business/consent?version=${encodeURIComponent(version)}`);
}

export function acceptBusinessConsent(version: string): Promise<BusinessConsent> {
  return apiFetch("/business/consent", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ version }),
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

export function getBusinessReceiptPage(view: "inbox" | "all", signal?: AbortSignal): Promise<{ items: ReceiptSummary[]; activity: ReceiptActivityCounts }> {
  return apiFetch(`/business/receipts?view=${view}`, { signal });
}

export async function listBusinessReceipts(
  view: "inbox" | "all",
): Promise<ReceiptSummary[]> {
  const page = await apiFetch<{ items: ReceiptSummary[] }>(
    `/business/receipts?view=${view}`,
  );
  return page.items;
}

export async function getBusinessReceipt(id: string, signal?: AbortSignal): Promise<ReceiptDetail> {
  return apiFetch(`/business/receipts/${encodeURIComponent(id)}`, { signal });
}

export async function getBusinessExpense(expenseId: string): Promise<BusinessExpenseDetail> {
  return apiFetch<BusinessExpenseDetail>(`/business/expenses/${encodeURIComponent(expenseId)}`);
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

/** Retry-After as seconds or an HTTP date, in milliseconds from now; null when absent or unreadable. */
export function retryAfterMs(header: string | null, now = Date.now()): number | null {
  if (header === null || header.trim() === "") return null;
  const seconds = Number(header);
  if (Number.isFinite(seconds)) return Math.max(0, seconds * 1000);
  const at = Date.parse(header);
  return Number.isNaN(at) ? null : Math.max(0, at - now);
}

/** Bytes of one upload sent so far; `total` is the whole file. */
export type UploadProgressListener = (sent: number, total: number) => void;

type UploadError = Error & { status: number; code: string; retryAfterMs: number | null };

function uploadError(status: number, body: string, retryAfter: string | null): UploadError {
  let code: string | undefined;
  try {
    code = (JSON.parse(body) as { code?: string }).code;
  } catch {
    code = undefined;
  }
  const error = new Error(code ?? `API error ${status}`) as UploadError;
  error.status = status;
  error.code = code ?? "unknown";
  error.retryAfterMs = retryAfterMs(retryAfter);
  return error;
}

/**
 * One receipt file to the Inbox. With a progress listener the body goes over
 * XMLHttpRequest, the one browser API that reports bytes sent; a lost
 * connection rejects with a TypeError, as fetch does, so it reads as offline.
 */
export async function uploadBusinessReceipt(
  file: File,
  consentToPrepare: boolean,
  idempotencyKey: string,
  /** Null leaves the header out so the server detects the type; a picked type turns detection off. */
  documentType: "recibo" | "venta" | null = null,
  onProgress?: UploadProgressListener,
): Promise<ReceiptSummary> {
  const authHeaders = await authenticatedRequestHeaders();
  const headers = argusApiRequestHeaders(
    {
      "Content-Type": file.type,
      "Idempotency-Key": idempotencyKey,
      "X-Document-Filename": encodeURIComponent(file.name),
      ...(documentType ? { "X-Document-Type": documentType } : {}),
      ...(consentToPrepare ? { "X-Extraction-Consent": "true" } : {}),
    },
    authHeaders,
  );
  const url = `${ARGUS_API_BASE_URL}/business/receipts`;
  if (onProgress && typeof XMLHttpRequest !== "undefined") {
    return new Promise<ReceiptSummary>((resolve, reject) => {
      const request = new XMLHttpRequest();
      request.open("POST", url);
      request.withCredentials = true;
      headers.forEach((value, key) => request.setRequestHeader(key, value));
      request.upload.onprogress = (event) => onProgress(event.loaded, event.lengthComputable ? event.total : file.size);
      request.onload = () => {
        if (request.status >= 200 && request.status < 300) {
          try {
            resolve(JSON.parse(request.responseText) as ReceiptSummary);
          } catch (error) {
            reject(error);
          }
        } else {
          reject(uploadError(request.status, request.responseText, request.getResponseHeader("Retry-After")));
        }
      };
      request.onerror = () => reject(new TypeError("Network request failed"));
      request.onabort = () => reject(new TypeError("Upload aborted"));
      request.send(file);
    });
  }
  const response = await fetch(url, {
    method: "POST",
    body: file,
    credentials: "include",
    headers,
  });
  if (!response.ok) throw uploadError(response.status, await response.text().catch(() => ""), response.headers.get("Retry-After"));
  return response.json() as Promise<ReceiptSummary>;
}

/** A source fetch that never answers ends here, so the preview can say so and offer a retry instead of loading forever. */
export const RECEIPT_SOURCE_TIMEOUT_MS = 30_000;

export async function fetchBusinessReceiptSource(id: string, options: { timeoutMs?: number } = {}): Promise<Blob> {
  const authHeaders = await authenticatedRequestHeaders();
  const response = await fetch(
    `${ARGUS_API_BASE_URL}/business/receipts/${encodeURIComponent(id)}/source`,
    { credentials: "include", headers: argusApiRequestHeaders(undefined, authHeaders), signal: AbortSignal.timeout(options.timeoutMs ?? RECEIPT_SOURCE_TIMEOUT_MS) },
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
export type BusinessAccessInvite = { id: string; email: string; created_at: string; expires_at: string; state: "pending" | "expired" };
export type BusinessAccess = { grants: BusinessAccessGrant[]; invites: BusinessAccessInvite[]; invite_delivery?: "not_configured" | "accepted" | "failed" | null };

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

export async function resendBusinessAccessInvite(id: string): Promise<BusinessAccess> {
  return apiFetch(`/business/access/invites/${encodeURIComponent(id)}/resend`, { method: "POST" });
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
