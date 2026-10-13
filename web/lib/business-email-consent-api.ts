import { authenticatedRequestHeaders } from "./chat-auth-ownership";
import { ARGUS_API_BASE_URL, argusApiRequestHeaders } from "./argus-api-transport";
import type { BusinessEmailAIReading, BusinessEmailIntake } from "./business-email";

/** The owner's permission to read emailed receipts with AI. The backend owns every fact. */

export type EmailReadingError = Error & { status: number; code: string };

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
    throw Object.assign(new Error("Email AI permission unavailable"), {
      status: response.status,
      code: typeof problem.code === "string" ? problem.code : "unknown",
    }) as EmailReadingError;
  }
  return (response.status === 204 ? undefined : await response.json()) as T;
}

export function getEmailIntake(language?: string): Promise<BusinessEmailIntake> {
  return request(`/business/email${language ? `?language=${encodeURIComponent(language)}` : ""}`);
}

export function enableEmailReading(disclosureToken: string, idempotencyKey: string, language?: string): Promise<BusinessEmailAIReading> {
  return request("/business/email/ai-consent", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ action: "enable", disclosure_token: disclosureToken, ...(language ? { language } : {}) }),
  });
}

export function declineEmailReading(idempotencyKey: string): Promise<BusinessEmailAIReading> {
  return request("/business/email/ai-consent", {
    method: "POST",
    headers: { "Idempotency-Key": idempotencyKey },
    body: JSON.stringify({ action: "decline" }),
  });
}

export function revokeEmailReading(): Promise<void> {
  return request("/business/email/ai-consent", { method: "DELETE" });
}

export type EmailReadingProblem = "stale" | "owner" | "unavailable" | "failed";

export function emailReadingProblem(error: unknown): EmailReadingProblem {
  const { status, code } = (error ?? {}) as Partial<EmailReadingError>;
  if (status === 409) return "stale";
  if (code === "business_owner_required" || code === "business_permission_denied") return "owner";
  if (status === 503 || status === 404) return "unavailable";
  return "failed";
}

/** The model names the owner is agreeing to, without repeats. */
export function readingModels(reading: BusinessEmailAIReading): string[] {
  const routes = [...(reading.route?.interpretation ?? []), ...(reading.route?.reply ?? [])];
  return [...new Set(routes.map((route) => route.model))];
}

/** The owner may agree only to a disclosure the server marks available and signed with a token. */
export function canAgreeToReading(reading: BusinessEmailAIReading | null | undefined): reading is BusinessEmailAIReading & { disclosure_token: string } {
  return (
    !!reading &&
    reading.available &&
    reading.owner &&
    reading.route !== null &&
    (reading.disclosure?.trim().length ?? 0) > 0 &&
    typeof reading.disclosure_token === "string" &&
    /^[a-f0-9]{64}$/.test(reading.disclosure_token)
  );
}

export type EmailReadingClient = {
  enable: (disclosureToken: string, idempotencyKey: string, language?: string) => Promise<BusinessEmailAIReading>;
  decline: (idempotencyKey: string) => Promise<BusinessEmailAIReading>;
  revoke: () => Promise<void>;
  read: (language?: string) => Promise<BusinessEmailIntake>;
  newKey: () => string;
};

export const liveEmailReadingClient: EmailReadingClient = {
  enable: enableEmailReading,
  decline: declineEmailReading,
  revoke: revokeEmailReading,
  read: getEmailIntake,
  newKey: () => crypto.randomUUID(),
};

/**
 * One tap on the settings switch. Returns the state the screen should show.
 * A failed call throws and the caller keeps the old state. After a revoke
 * succeeds the answer is off even if the follow-up read fails.
 */
export async function toggleEmailReading(
  reading: BusinessEmailAIReading,
  client: EmailReadingClient = liveEmailReadingClient,
  language?: string,
): Promise<BusinessEmailAIReading> {
  if (reading.state === "on") {
    await client.revoke();
    const off: BusinessEmailAIReading = { ...reading, state: "off", consented_at: null, consented_by: null };
    return client.read(language).then((intake) => intake.ai_reading ?? off).catch(() => off);
  }
  if (!canAgreeToReading(reading)) throw new Error("Email AI reading cannot be turned on");
  return client.enable(reading.disclosure_token, client.newKey(), language);
}
