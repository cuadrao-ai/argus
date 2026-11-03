import type { AccountDeletionEligibility } from "./account-deletion-api";

/* The sample preview has no deletion rule behind it, so it fakes the server's
 * answer from the address: /dev/business-preview?deletion=allowed|owner|closed|not_allowed|loading,
 * with &lifecycle=on to show the Transferir and Cerrar links. Only in a
 * development build with mock auth, and only on that page. */

const SAMPLE_BUSINESSES = [
  { kind: "business_owner" as const, business_id: "sample-business-1", business_name: "Colmado Peña" },
  { kind: "business_owner" as const, business_id: "sample-business-2", business_name: "Ferretería La Esquina" },
];

const CLOSED_SAMPLE = { kind: "closed_business" as const, business_id: "sample-business-3", business_name: "Taller Brisa", purge_at: "2026-12-02T16:00:00Z" };

function previewParams(): URLSearchParams | null {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") return null;
  if (typeof window === "undefined" || !window.location.pathname.startsWith("/dev/business-preview")) return null;
  return new URLSearchParams(window.location.search);
}

/** The faked read, or null outside the preview or when the address names no state. */
export function previewDeletionEligibility(): (() => Promise<AccountDeletionEligibility>) | null {
  const state = previewParams()?.get("deletion");
  if (state === "allowed") return async () => ({ allowed: true, blockers: [], notices: [] });
  if (state === "owner") return async () => ({ allowed: false, blockers: SAMPLE_BUSINESSES, notices: [] });
  if (state === "closed") return async () => ({ allowed: true, blockers: [], notices: [CLOSED_SAMPLE] });
  if (state === "not_allowed") return async () => ({ allowed: false, blockers: [{ kind: "not_allowed" }], notices: [] });
  if (state === "loading") return () => new Promise<AccountDeletionEligibility>(() => undefined);
  return null;
}

/** The preview's stand-in for the lifecycle controls flag. */
export function previewLifecycleControls(): boolean | null {
  const value = previewParams()?.get("lifecycle");
  return value === "on" ? true : value === "off" ? false : null;
}
