import { apiFetch } from "./argus-api-transport";

/**
 * GET /business/activity (#1407): who changed what in the working Business, newest first. The working Business is
 * the chosen grant's (apiFetch sends X-Business-Grant), else the caller's own. Read-only; 25 rows a page.
 */
export type BusinessActivityActor = { display_name: string; kind: "member" | "owner_via_agent" | "extractor" };
export type BusinessActivityItem = {
  id: string;
  occurred_at: string;
  actor: BusinessActivityActor;
  action: string;
  object: { kind: "draft" | "grant" | "invite"; id: string } | null;
};
export type BusinessActivityPage = { items: BusinessActivityItem[]; next_cursor: string | null };

export function getBusinessActivity(cursor: string | null, signal?: AbortSignal): Promise<BusinessActivityPage> {
  const query = new URLSearchParams({ limit: "25" });
  if (cursor) query.set("cursor", cursor);
  return apiFetch(`/business/activity?${query}`, { signal });
}
