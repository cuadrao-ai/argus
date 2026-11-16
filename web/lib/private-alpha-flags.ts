export const omnisearchEnabled =
  process.env.NEXT_PUBLIC_OMNISEARCH_ENABLED !== "false";

// Research rail presentation: entry copy, range-spanning chips, the signed-in
// empty-chat greeting, and confirmation peer offers. Default off; flag-off
// behavior stays byte-identical to the pre-rail surface.
export const researchRailEnabled =
  process.env.NEXT_PUBLIC_RESEARCH_RAIL_ENABLED === "true";

export function guestAccessEnabledFromEnv(value: string | undefined): boolean {
  if (value === undefined || value.trim() === "") return true;
  const normalized = value.trim().toLowerCase();
  if (["1", "true", "yes", "on"].includes(normalized)) return true;
  return false;
}

export const guestAccessEnabled = guestAccessEnabledFromEnv(
  process.env.NEXT_PUBLIC_GUEST_ACCESS_ENABLED,
);

// Default off, and it stays off when this lane lands. Turning sharing on is a
// separate founder decision from merging it.
export const evidenceReceiptSharingEnabled =
  process.env.NEXT_PUBLIC_EVIDENCE_RECEIPT_SHARING_ENABLED === "true";

// Business is the only web app. Unset is on. The string "false" restores the
// consumer web (root, guest chat, and /chat).
export function businessOnlyWebFromEnv(value: string | undefined): boolean {
  return value !== "false";
}

export const businessOnlyWebEnabled = businessOnlyWebFromEnv(
  process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB,
);

// Statement match cards. Default off.
// CUADRAO wins when both names are set.
export const businessBankMatchingEnabled = (() => {
  const cuadrao = process.env.NEXT_PUBLIC_CUADRAO_BUSINESS_BANK_MATCHING_ENABLED;
  const legacy = process.env.NEXT_PUBLIC_BUSINESS_BANK_MATCHING_ENABLED;
  const value = (cuadrao ?? legacy ?? "").trim().toLowerCase();
  return ["1", "true", "yes", "on"].includes(value);
})();

// Transferir and Cerrar on Negocio. Default off for the pilot.
export function businessLifecycleControlsEnabled(
  value: string | undefined = process.env.NEXT_PUBLIC_CUADRAO_BUSINESS_LIFECYCLE_CONTROLS_ENABLED,
): boolean {
  return value === "true";
}
