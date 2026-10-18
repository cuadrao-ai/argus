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
