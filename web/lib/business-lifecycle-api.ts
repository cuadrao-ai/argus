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

const memberIdentity = z.object({ grant_id: z.uuid(), name: z.string() });
const transferMember = z.discriminatedUnion("eligible", [
  memberIdentity.extend({ eligible: z.literal(true), reason: z.null() }),
  memberIdentity.extend({ eligible: z.literal(false), reason: z.enum(["account_unavailable", "not_editor", "email_unconfirmed", "owns_open_business"]) }),
]);
const ownedBusiness = z.object({
  space_id: z.uuid(), name: z.string(), grant_id: z.uuid(),
  member_count: z.number().int().nonnegative(),
  reopen_until: z.iso.datetime({ offset: true }),
  export_windows: z.array(z.object({ start: z.iso.date(), end: z.iso.date() })),
  members: z.array(transferMember),
});
export type OwnedBusiness = z.infer<typeof ownedBusiness>;

export async function getOwnedBusinessSpaces(signal?: AbortSignal): Promise<OwnedBusiness[]> {
  return z.object({ spaces: z.array(ownedBusiness) }).parse(await apiFetch<unknown>("/business/owned-spaces", { signal })).spaces;
}

export function businessLifecycleHref(spaceId: string, action: "close" | "transfer"): string {
  return `/biz?lifecycle=${action}&business=${encodeURIComponent(spaceId)}`;
}

export function businessDeadlineParts(value: string, locale: string) {
  const date = new Date(value);
  const options = { timeZone: "America/Santo_Domingo" };
  return {
    purgeDate: date.toLocaleDateString(locale, { ...options, day: "numeric", month: "long", year: "numeric" }),
    purgeTime: date.toLocaleTimeString(locale, { ...options, hour: "numeric", minute: "2-digit" }),
  };
}

export function businessLifecycleErrorKey(error: unknown, fallback: string): string {
  const code = typeof error === "object" && error !== null && "code" in error && typeof error.code === "string" ? error.code : "";
  const known: Record<string, string> = {
    business_name_mismatch: "name_mismatch",
    business_record_not_found: "business_unavailable",
    business_unavailable: "business_unavailable",
    business_grant_not_live: "business_unavailable",
    business_already_open: "already_open",
    business_reopen_expired: "reopen_expired",
    business_transfer_pending: "transfer_pending",
    business_transfer_target_invalid: "target_invalid",
    business_transfer_expired: "transfer_expired",
    business_transfer_not_pending: "transfer_not_pending",
    business_transfer_confirmation_required: "refresh_required",
  };
  return `business.lifecycle.errors.${known[code] ?? fallback}`;
}
