import { unauthenticatedApiFetch } from "./argus-api-transport";

export type AccountAccessMode = "open" | "invite_only" | "unavailable";

export function parseAccountAccessMode(payload: unknown): AccountAccessMode {
  const mode =
    typeof payload === "object" && payload !== null
      ? (payload as { access_mode?: unknown }).access_mode
      : undefined;
  return mode === "open" || mode === "invite_only" ? mode : "unavailable";
}

export async function readAccountAccessMode(): Promise<AccountAccessMode> {
  try {
    return parseAccountAccessMode(
      await unauthenticatedApiFetch<unknown>("/auth/access-mode", { method: "GET" }),
    );
  } catch {
    return "unavailable";
  }
}

export function defaultLandingAuthMode(mode: AccountAccessMode): "intro" | "login" {
  return mode === "open" ? "intro" : "login";
}

const CONTACT_PAGE_URL = {
  "es-419": "https://cuadrao.ai/contacto",
  en: "https://cuadrao.ai/en/contact",
} as const;

export function contactPageHref(language: string | undefined): string {
  return language?.toLowerCase().startsWith("en")
    ? CONTACT_PAGE_URL.en
    : CONTACT_PAGE_URL["es-419"];
}
