import type { TaxId } from "./business-dgii";
import type { ArgusLanguage } from "./language-features";
import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { CUADRAO_API_BASE_URL, argusApiRequestHeaders } from "./argus-api-transport";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "./browser-auth-generation";

/** The signed-in person's WhatsApp sender link. The backend owns every fact. */

export type WhatsAppLinkCode = {
  code: string;
  message_text: string;
  expires_at: string;
  wa_me_url: string | null;
  qr_data_url: string | null;
};

export type WhatsAppLinkStatus = {
  disclosure: string;
  disclosure_token: string;
  linked: boolean;
  last4: string | null;
  linked_at: string | null;
  receiving_businesses: { space_id: string; name: string; tax_id: TaxId }[];
  held_count: number;
  reply_language: "en" | "es-419" | null;
};

export type WhatsAppLinkError = Error & { status: number; code: string };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const generation = browserAuthGeneration();
  const authHeaders = await authenticatedRequestHeaders();
  requireBrowserAuthGeneration(generation);
  const response = await fetch(`${CUADRAO_API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: argusApiRequestHeaders(options?.headers, authHeaders, null),
  });
  requireBrowserAuthGeneration(generation);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { code?: unknown; detail?: unknown };
    const problem = typeof body.detail === "object" && body.detail !== null ? (body.detail as { code?: unknown }) : body;
    throw Object.assign(new Error("WhatsApp link unavailable"), {
      status: response.status,
      code: typeof problem.code === "string" ? problem.code : "unknown",
    }) as WhatsAppLinkError;
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function getWhatsAppLink(language: ArgusLanguage, signal?: AbortSignal): Promise<WhatsAppLinkStatus> {
  return request(`/whatsapp/link?language=${language}`, { signal });
}

export function createWhatsAppLinkCode(language: ArgusLanguage, disclosureToken: string): Promise<WhatsAppLinkCode> {
  return request("/whatsapp/link-codes", { method: "POST", body: JSON.stringify({ language, disclosure_token: disclosureToken }) });
}

export function unlinkWhatsApp(): Promise<void> {
  return request("/whatsapp/link", { method: "DELETE" });
}

export type WhatsAppLinkProblem = "unavailable" | "setup_required" | "rate_limited" | "stale" | "failed";

export function whatsAppLinkProblem(error: unknown): WhatsAppLinkProblem {
  const { status, code } = (error ?? {}) as Partial<WhatsAppLinkError>;
  if (code === "whatsapp_setup_required") return "setup_required";
  if (status === 404) return "unavailable";
  if (status === 429) return "rate_limited";
  if (status === 409) return "stale";
  return "failed";
}

export function revokeWhatsAppAI(): Promise<void> {
  return request("/whatsapp/ai-consent", { method: "DELETE" });
}
