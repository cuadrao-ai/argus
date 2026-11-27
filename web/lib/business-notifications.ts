/**
 * The bell's list: the notices the server holds for the signed-in person,
 * from any Business. The server owns the list and what was read; the web
 * renders them and never builds either.
 */

import { z } from "zod";

import { apiFetch } from "./argus-api-transport";

const notice = z.object({
  id: z.string(),
  kind: z.literal("invitation_received"),
  business_id: z.string(),
  business_name: z.string().nullable(),
  requested_role: z.enum(["owner", "admin", "editor", "viewer"]),
  unread: z.boolean(),
});
const notices = z.object({ items: z.array(notice) });

/** An invitation addressed to the person; `id` is the invitation's id. */
export type BusinessNotice = z.infer<typeof notice>;

export async function getBusinessNotices(signal?: AbortSignal): Promise<BusinessNotice[]> {
  return notices.parse(await apiFetch<unknown>("/business/notifications", { signal })).items;
}

export async function markBusinessNoticesRead(ids: readonly string[]): Promise<void> {
  await apiFetch<unknown>("/business/notifications/read", { method: "POST", body: JSON.stringify({ ids }) });
}
