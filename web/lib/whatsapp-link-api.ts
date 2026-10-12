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

export type WhatsAppAIConsent = {
  linked: boolean;
  available: boolean;
  reason: string | null;
  last4: string | null;
  scope_version: number;
  purpose: string;
  /** The disclosure the owner reads before agreeing, verbatim from the server. */
  disclosure: string;
  route: {
    gateway: string;
    interpretation: { model: string }[];
    reply: { model: string }[];
  } | null;
  /** Binds the enable request to the exact disclosure shown. */
  disclosure_token: string | null;
  enabled: boolean;
  consented_at: string | null;
  revoked_at: string | null;
};

export function getWhatsAppAIConsent(): Promise<WhatsAppAIConsent> {
  return request("/whatsapp/ai-consent");
}

export function enableWhatsAppAI(
  disclosureToken: string,
  idempotencyKey: string,
): Promise<WhatsAppAIConsent> {
  return request("/whatsapp/ai-consent", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ action: "enable", disclosure_token: disclosureToken }),
  });
}

export function revokeWhatsAppAI(): Promise<void> {
  return request("/whatsapp/ai-consent", { method: "DELETE" });
}

/** The model names the owner is agreeing to, without repeats. */
export function consentModels(consent: WhatsAppAIConsent): string[] {
  const routes = [...(consent.route?.interpretation ?? []), ...(consent.route?.reply ?? [])];
  return [...new Set(routes.map((route) => route.model))];
}

/** The owner may agree only to a disclosure the server marks available and unsigned. */
export function canEnableAI(consent: WhatsAppAIConsent): consent is WhatsAppAIConsent & {
  disclosure_token: string;
} {
  return (
    consent.linked &&
    consent.available &&
    !consent.enabled &&
    consent.route !== null &&
    consent.disclosure.trim().length > 0 &&
    typeof consent.disclosure_token === "string" &&
    /^[a-f0-9]{64}$/.test(consent.disclosure_token)
  );
}
