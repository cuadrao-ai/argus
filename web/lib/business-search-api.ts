import { apiFetch } from "./argus-api-transport";
import type { BusinessAccount, BusinessExpense, ReceiptSummary } from "./business-api";
import type { BusinessEmailDelivery } from "./business-email";

/**
 * The Business search over `/business/search`. The backend owns what matches
 * and in which list; this module reads each list defensively so a backend
 * that predates a list still answers with it empty.
 */

export const BUSINESS_SEARCH_KINDS = ["expenses", "ventas", "receipts", "accounts", "email_deliveries", "email_senders"] as const;
export type BusinessSearchKind = (typeof BUSINESS_SEARCH_KINDS)[number];

export type BusinessSearchEmail = {
  id: string;
  sender: string | null;
  subject: string | null;
  received_at: string;
  state: BusinessEmailDelivery["state"];
  inbox_group: "bandeja" | "remitentes_nuevos" | null;
};

export type BusinessSearchSender = {
  id: string;
  kind: "address" | "domain";
  value: string;
  status: "authorized" | "blocked";
};

type Lists = {
  expenses: BusinessExpense[];
  /** In a venta, `merchant` holds the client. */
  ventas: BusinessExpense[];
  receipts: ReceiptSummary[];
  accounts: BusinessAccount[];
  email_deliveries: BusinessSearchEmail[];
  email_senders: BusinessSearchSender[];
};

/**
 * Business records matching a query, each list capped by `limit`. A receipt
 * whose expense also matched is only under its expense, as `receipt_id`.
 * `next_cursors[list]` is the cursor for that list's next page, or null at its end.
 */
export type BusinessSearchResult = Lists & { next_cursors: Partial<Record<BusinessSearchKind, string | null>> };

export const SEARCH_INVALID_CURSOR = "business_search_invalid_cursor";
export const SEARCH_STALE_CURSOR = "business_search_stale_cursor";

type ApiFailure = { status?: number; code?: string };

/** The cursor belongs to a result that changed since: search again from page 1. */
export function isStaleSearchCursor(error: unknown): boolean {
  const { status, code } = (error ?? {}) as ApiFailure;
  return status === 409 || code === SEARCH_STALE_CURSOR;
}

/** The cursor is not one the server issued: it can never work, so only page 1 can. */
export function isInvalidSearchCursor(error: unknown): boolean {
  return ((error ?? {}) as ApiFailure).code === SEARCH_INVALID_CURSOR;
}

/** The endpoint is not there on this backend yet. */
export function isMissingEndpoint(error: unknown): boolean {
  const { status } = (error ?? {}) as ApiFailure;
  return status === 404 || status === 405 || status === 501;
}

function list<T>(value: unknown): T[] {
  return Array.isArray(value) ? (value as T[]) : [];
}

function cursors(value: unknown): BusinessSearchResult["next_cursors"] {
  const out: BusinessSearchResult["next_cursors"] = {};
  if (!value || typeof value !== "object") return out;
  for (const kind of BUSINESS_SEARCH_KINDS) {
    const cursor = (value as Record<string, unknown>)[kind];
    if (typeof cursor === "string" && cursor) out[kind] = cursor;
  }
  return out;
}

/** Every list present, whatever the backend sent; a missing or malformed one is empty. */
export function parseBusinessSearch(raw: unknown): BusinessSearchResult {
  const body = (raw && typeof raw === "object" ? raw : {}) as Record<string, unknown>;
  return {
    expenses: list(body.expenses),
    ventas: list(body.ventas),
    receipts: list(body.receipts),
    accounts: list(body.accounts),
    email_deliveries: list(body.email_deliveries),
    email_senders: list(body.email_senders),
    next_cursors: cursors(body.next_cursors),
  };
}

const PAGE = 5;

/** Page 1 of every list. */
export async function searchBusiness(q: string, limit = PAGE): Promise<BusinessSearchResult> {
  const query = new URLSearchParams({ q, limit: String(limit) });
  return parseBusinessSearch(await apiFetch<unknown>(`/business/search?${query}`));
}

/** The next page of one list; the other lists come back empty. */
export async function searchBusinessMore(q: string, kind: BusinessSearchKind, cursor: string, limit = PAGE): Promise<BusinessSearchResult> {
  const query = new URLSearchParams({ q, limit: String(limit), kind, cursor });
  return parseBusinessSearch(await apiFetch<unknown>(`/business/search?${query}`));
}

export type BusinessSearchRecent = { id: string; q: string; searched_at: string };

/** What this person searched lately, newest first. */
export async function listBusinessSearchRecents(): Promise<BusinessSearchRecent[]> {
  const body = await apiFetch<{ items?: unknown }>("/business/search/recents");
  return list<BusinessSearchRecent>(body?.items).filter((item) => typeof item?.id === "string" && typeof item.q === "string");
}

/** These writes answer 201 or 204 with no body, which the shared fetch then fails to read as JSON. */
async function writeWithoutBody(path: string, init: RequestInit): Promise<void> {
  try {
    await apiFetch(path, init);
  } catch (error) {
    if (!(error instanceof SyntaxError)) throw error;
  }
}

export async function addBusinessSearchRecent(q: string): Promise<void> {
  await writeWithoutBody("/business/search/recents", { method: "POST", body: JSON.stringify({ q }) });
}

export async function removeBusinessSearchRecent(id: string): Promise<void> {
  await writeWithoutBody(`/business/search/recents/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export async function clearBusinessSearchRecents(): Promise<void> {
  await writeWithoutBody("/business/search/recents", { method: "DELETE" });
}

/** A result was opened: it ranks first the next time it matches. */
export async function recordBusinessSearchOpen(kind: BusinessSearchKind, id: string): Promise<void> {
  await writeWithoutBody("/business/search/opens", { method: "POST", body: JSON.stringify({ kind, id }) });
}
