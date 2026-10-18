import { z } from "zod";
import { apiFetch } from "./argus-api-transport";

const transferResult = z.object({
  id: z.uuid(),
  space_id: z.uuid(),
  status: z.enum(["pending", "accepted", "cancelled", "declined", "expired"]),
  expires_at: z.iso.datetime({ offset: true }).nullable().optional(),
});
export type BusinessTransferResult = z.infer<typeof transferResult>;
const transferDetails = transferResult.extend({ business_name: z.string(), owner_name: z.string(), target_name: z.string(), role: z.enum(["owner", "target"]), grant_id: z.uuid() });
export type BusinessTransferDetails = z.infer<typeof transferDetails>;

export async function discoverBusinessTransfers(signal?: AbortSignal): Promise<BusinessTransferDetails[]> {
  return z.object({ transfers: z.array(transferDetails) }).parse(await apiFetch<unknown>("/business/ownership-transfers", { signal })).transfers;
}

export async function requestBusinessTransfer({ spaceId, targetGrantId, confirmation, idempotencyKey, signal }: {
  spaceId: string;
  targetGrantId: string;
  confirmation: string;
  idempotencyKey: string;
  signal?: AbortSignal;
}): Promise<BusinessTransferResult> {
  const result = transferResult.parse(await apiFetch<unknown>(`/business/spaces/${encodeURIComponent(spaceId)}/ownership-transfers`, {
    method: "POST", headers: { "Idempotency-Key": idempotencyKey }, signal,
    body: JSON.stringify({ target_grant_id: targetGrantId, confirmation }),
  }));
  if (result.space_id !== spaceId) throw new Error("business_transfer_scope_changed");
  return result;
}

export async function respondToBusinessTransfer({ transferId, action, signal }: {
  transferId: string;
  action: "accept" | "decline" | "withdraw";
  signal?: AbortSignal;
}): Promise<BusinessTransferResult> {
  const result = transferResult.parse(await apiFetch<unknown>(`/business/ownership-transfers/${encodeURIComponent(transferId)}/${action}`, { method: "POST", signal }));
  if (result.id !== transferId) throw new Error("business_transfer_command_changed");
  return result;
}
