import { apiFetch } from "./argus-api-transport";
import type { PersonName } from "./person-name";

/**
 * GET /business/activity (#1407): who changed what in the working Business, newest first. The working Business is
 * the chosen grant's (apiFetch sends X-Business-Grant), else the caller's own. Read-only; 25 rows a page.
 */
/** A person named as `PersonName` says; automated work names no one, and the screen words it. */
export type BusinessActivityActor =
  | (PersonName & { kind: "member" | "owner_via_agent" })
  | { kind: "extractor"; display_name: null; email?: null; shown_as: null };
export type BusinessActivityItem = {
  id: string;
  occurred_at: string;
  /** null when the source recorded no actor. */
  actor: BusinessActivityActor | null;
  action: string;
  /** `purged`: the document is gone for good, so it has no label and nothing opens it. */
  object: { kind: "draft" | "receipt" | "grant" | "invite"; id: string; label?: string; purged?: boolean } | null;
};
export type BusinessActivityPage = { items: BusinessActivityItem[]; next_cursor: string | null };

export function getBusinessActivity(cursor: string | null, signal?: AbortSignal, q?: string): Promise<BusinessActivityPage> {
  const query = new URLSearchParams({ limit: "25" });
  if (cursor) query.set("cursor", cursor);
  if (q) query.set("q", q);
  return apiFetch(`/business/activity?${query}`, { signal });
}

/**
 * The rows whose person or named object holds `q`, matched by the server. One answer scans a bounded stretch of the
 * history, so it can come back empty with a cursor: this follows it to the first rows, or to the end.
 */
export async function searchBusinessActivity(q: string, cursor: string | null = null): Promise<BusinessActivityPage> {
  let page = await getBusinessActivity(cursor, undefined, q);
  while (page.items.length === 0 && page.next_cursor) page = await getBusinessActivity(page.next_cursor, undefined, q);
  return page;
}
