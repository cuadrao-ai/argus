import type { AccountDeletionEligibility } from "./account-deletion-api";

/* The sample preview has no deletion rule behind it, so it fakes the server's
 * answer from the address: /dev/business-preview?deletion=allowed|owner|closed|not_allowed|unavailable|slow|loading,
 * with &owned=1..8 for how many Businesses block it (3 by default) and
 * &lifecycle=on|off for the transfer and close controls flag. Solicitar
 * eliminación answers as filed. Only in a development build with mock auth,
 * and only on that page. */

const SAMPLE_NAMES = [
  "Cafetería Malecón",
  "Colmado La Esquina",
  "Farmacia San Rafael",
  "Ferretería Los Pinos",
  "Panadería El Trigal",
  "Repuestos del Cibao",
  "Salón Brisa",
  "Taller Hermanos Peña",
];

function sampleBusinesses(owned: string | null) {
  const count = Math.min(Math.max(Number(owned) || 3, 1), SAMPLE_NAMES.length);
  const names = count === 3 ? ["Colmado La Esquina", "Ferretería Los Pinos", "Salón Brisa"] : SAMPLE_NAMES.slice(0, count);
  return names.map((name, index) => ({ kind: "business_owner" as const, business_id: `sample-business-${index + 1}`, business_name: name }));
}

const CLOSED_SAMPLE = { kind: "closed_business" as const, business_id: "sample-business-3", business_name: "Taller Brisa", purge_at: "2026-12-02T16:00:00Z" };

function previewParams(): URLSearchParams | null {
  if (process.env.NODE_ENV !== "development" || process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") return null;
  if (typeof window === "undefined" || !window.location.pathname.startsWith("/dev/business-preview")) return null;
  return new URLSearchParams(window.location.search);
}

/** The faked read, or null outside the preview or when the address names no state. */
export function previewDeletionEligibility(): (() => Promise<AccountDeletionEligibility>) | null {
  const params = previewParams();
  const state = params?.get("deletion");
  const SAMPLE_BUSINESSES = sampleBusinesses(params?.get("owned") ?? null);
  if (state === "allowed") return async () => ({ allowed: true, blockers: [], notices: [] });
  if (state === "owner") return async () => ({ allowed: false, blockers: SAMPLE_BUSINESSES, notices: [] });
  if (state === "closed") return async () => ({ allowed: true, blockers: [], notices: [CLOSED_SAMPLE] });
  if (state === "not_allowed") return async () => ({ allowed: false, blockers: [{ kind: "not_allowed" }], notices: [] });
  if (state === "unavailable") return async () => { throw Object.assign(new Error("account_deletion_unavailable"), { status: 503, code: "account_deletion_unavailable", requestId: "preview-ref-503" }); };
  if (state === "slow") return () => new Promise<AccountDeletionEligibility>((resolve) => setTimeout(() => resolve({ allowed: false, blockers: SAMPLE_BUSINESSES, notices: [] }), 4000));
  if (state === "loading") return () => new Promise<AccountDeletionEligibility>(() => undefined);
  return null;
}

/** The preview's Solicitar eliminación: filed, as the server answers an owner. */
export function previewSupportRequest(): (() => Promise<void>) | null {
  return previewParams()?.get("deletion") ? async () => undefined : null;
}

/** The preview's stand-in for the lifecycle controls flag. */
export function previewLifecycleControls(): boolean | null {
  const value = previewParams()?.get("lifecycle");
  return value === "on" ? true : value === "off" ? false : null;
}
