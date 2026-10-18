import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

const lifecycleResult = z.object({
  space_id: z.uuid(),
  name: z.string(),
  closed_at: z.iso.datetime({ offset: true }).nullable(),
  reopen_until: z.iso.datetime({ offset: true }).nullable(),
});
const closedBusinesses = z.object({ spaces: z.array(lifecycleResult) });
export type BusinessLifecycleResult = z.infer<typeof lifecycleResult>;
type BusinessCommand = { spaceId: string; idempotencyKey: string; signal?: AbortSignal };

/** Keep the original key when checking an uncertain command's outcome. */
export async function closeBusinessSpace({ spaceId, idempotencyKey, confirmation, signal }: BusinessCommand & { confirmation: string }): Promise<BusinessLifecycleResult> {
  return lifecycleResult.parse(await apiFetch<unknown>(`/business/spaces/${encodeURIComponent(spaceId)}/close`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, signal,
    body: JSON.stringify({ confirmation }),
  }));
}

export async function reopenBusinessSpace({ spaceId, idempotencyKey, signal }: BusinessCommand): Promise<BusinessLifecycleResult> {
  return lifecycleResult.parse(await apiFetch<unknown>(`/business/spaces/${encodeURIComponent(spaceId)}/reopen`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, signal,
  }));
}

export async function getClosedBusinessSpaces(signal?: AbortSignal): Promise<BusinessLifecycleResult[]> {
  return closedBusinesses.parse(await apiFetch<unknown>("/business/closed-spaces", { signal })).spaces;
}

const ownedBusiness = z.object({
  space_id: z.uuid(), name: z.string(), grant_id: z.uuid(),
  members: z.array(z.object({ grant_id: z.uuid(), name: z.string() })),
});
export type OwnedBusiness = z.infer<typeof ownedBusiness>;

export async function getOwnedBusinessSpaces(signal?: AbortSignal): Promise<OwnedBusiness[]> {
  return z.object({ spaces: z.array(ownedBusiness) }).parse(await apiFetch<unknown>("/business/owned-spaces", { signal })).spaces;
}

export function businessLifecycleHref(spaceId: string, action: "close" | "transfer"): string {
  return `/biz?lifecycle=${action}&business=${encodeURIComponent(spaceId)}`;
}
