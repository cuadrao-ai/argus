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

async function requestResponse(path: string, options?: RequestInit) {
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
  return { response, generation };
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const { response, generation } = await requestResponse(path, options);
  const result = response.status === 204 ? undefined : await response.json();
  requireBrowserAuthGeneration(generation);
  return result as T;
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

export type WhatsAppHeldFile = {
  id: string;
  reason: "no_buyer_rnc" | "no_match" | "two_matches" | "held_read_cap" | "read_failed" | "no_eligible_business";
  reading: boolean;
  held_at: string;
  expires_at: string;
  media_type: string;
  preview_url: string;
};

export type WhatsAppHeldFilesResponse = {
  files: WhatsAppHeldFile[];
  receiving_businesses: { space_id: string; name: string }[];
};

export function getWhatsAppHeldFiles(signal: AbortSignal): Promise<WhatsAppHeldFilesResponse> {
  return request("/whatsapp/held-files", { signal });
}

export function assignWhatsAppHeldFile(id: string, business_id: string, signal: AbortSignal): Promise<void> {
  return request(`/whatsapp/held-files/${encodeURIComponent(id)}/assign`, {
    method: "POST", body: JSON.stringify({ business_id }), signal,
  });
}

export async function readWhatsAppHeldPreview(url: string, signal: AbortSignal): Promise<Blob> {
  // Keep sender credentials on the configured API and within the sender's preview route.
  const match = /^\/api\/v1(\/whatsapp\/held-files\/[A-Za-z0-9_-]+\/preview)$/.exec(url);
  if (!match) throw new Error("Invalid held file preview path");
  const { response, generation } = await requestResponse(match[1], { signal, redirect: "error" });
  const blob = await response.blob();
  requireBrowserAuthGeneration(generation);
  return blob;
}
