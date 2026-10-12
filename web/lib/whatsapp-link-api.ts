import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { ARGUS_API_BASE_URL, argusApiRequestHeaders } from "./argus-api-transport";

/** The signed-in owner's WhatsApp sender link. The backend owns every fact. */

export type WhatsAppLinkCode = {
  code: string;
  message_text: string;
  expires_at: string;
  wa_me_url: string | null;
};

export type WhatsAppLinkStatus = {
  linked: boolean;
  last4: string | null;
  linked_at: string | null;
  reply_language: "en" | "es-419" | null;
};

export type WhatsAppLinkError = Error & { status: number; code: string };

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const authHeaders = await authenticatedRequestHeaders();
  const response = await fetch(`${ARGUS_API_BASE_URL}${path}`, {
    ...options,
    credentials: "include",
    cache: "no-store",
    headers: argusApiRequestHeaders(options?.headers, authHeaders),
  });
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

export function getWhatsAppLink(): Promise<WhatsAppLinkStatus> {
  return request("/whatsapp/link");
}

export function createWhatsAppLinkCode(language: "en" | "es-419"): Promise<WhatsAppLinkCode> {
  return request("/whatsapp/link-codes", { method: "POST", body: JSON.stringify({ language }) });
}

export function unlinkWhatsApp(): Promise<void> {
  return request("/whatsapp/link", { method: "DELETE" });
}

export type WhatsAppLinkProblem = "unavailable" | "space_missing" | "rate_limited" | "failed";

export function whatsAppLinkProblem(error: unknown): WhatsAppLinkProblem {
  const { status, code } = (error ?? {}) as Partial<WhatsAppLinkError>;
  if (code === "business_space_missing") return "space_missing";
  if (status === 404) return "unavailable";
  if (status === 429) return "rate_limited";
  return "failed";
}
