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

// Cuadrao Business owner pilot: overview, receipt inbox, review and expenses
// inside the chat shell on /biz. Default off until the connected pilot passes.
export function businessPilotEnabledFromEnv(
  value: string | undefined = process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED,
): boolean {
  return value === "true";
}

export const businessPilotEnabled = businessPilotEnabledFromEnv();

// Business is the only web app. Unset is on. The string "false" restores the
// consumer web (root, guest chat, and /chat).
export function businessOnlyWebFromEnv(value: string | undefined): boolean {
  return value !== "false";
}

export const businessOnlyWebEnabled = businessOnlyWebFromEnv(
  process.env.NEXT_PUBLIC_BUSINESS_ONLY_WEB,
);

// Business Preferencias WhatsApp number. Default off. The row stays hidden
// until intake is connected. Personal preferences do not read this flag.
export function businessWhatsappPreferencesEnabledFromEnv(
  value: string | undefined = process.env.NEXT_PUBLIC_BUSINESS_WHATSAPP_PREFERENCES_ENABLED,
): boolean {
  return value === "true";
}

export const businessWhatsappPreferencesEnabled =
  businessWhatsappPreferencesEnabledFromEnv();

// Business Buscar and its Ctrl/Cmd+K shortcut. Default off, and separate from
// the WhatsApp preferences flag so search can return on its own.
export function businessSearchEnabledFromEnv(
  value: string | undefined = process.env.NEXT_PUBLIC_BUSINESS_SEARCH_ENABLED,
): boolean {
  return value === "true";
}

export const businessSearchEnabled = businessSearchEnabledFromEnv();

export function businessSearchEntryEnabled(workspaceId: string | undefined): boolean {
  return workspaceId !== "business" || businessSearchEnabledFromEnv();
}
