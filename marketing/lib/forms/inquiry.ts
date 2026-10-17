import { PROVIDER_TIMEOUT_MS, type FormsConfig } from "./config";
import { clientKey, isSameOrigin, jsonResponse, logEvent, readJsonBody } from "./http";
import { WindowLimiter } from "./rate-limit";
import { isHoneypotFilled, validateInquiry, type InquiryInput } from "./validation";

export type InquiryDeps = {
  config: FormsConfig;
  fetch: typeof fetch;
  perClient: WindowLimiter;
  perEmail: WindowLimiter;
  overall: WindowLimiter;
};

export function inquiryText(input: InquiryInput): string {
  return [
    "Nuevo mensaje desde el sitio de Cuadrao",
    "",
    `Nombre: ${input.name}`,
    `Correo: ${input.email}`,
    `Idioma del sitio: ${input.locale}`,
    "",
    "Mensaje:",
    input.description || "(sin comentario)",
    "",
  ].join("\n");
}

// Resend remembers an Idempotency-Key for 24 hours and returns the original
// result for a repeat, so a double click or a retry after a lost response
// cannot send the message twice.
async function sendThroughResend(
  config: FormsConfig,
  input: InquiryInput,
  doFetch: typeof fetch,
): Promise<boolean> {
  const response = await doFetch(`${config.resendApiUrl}/emails`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${config.resendApiKey}`,
      "Content-Type": "application/json",
      "Idempotency-Key": `inquiry-${input.submissionId}`,
    },
    body: JSON.stringify({
      from: config.inquiryFrom,
      to: [config.inquiryTo],
      reply_to: input.email,
      subject: `Cuadrao: nueva consulta de ${input.name}`.slice(0, 200),
      text: inquiryText(input),
    }),
    signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
  });
  if (!response.ok) logEvent("inquiry_provider_rejected", { status: response.status });
  return response.ok;
}

export async function handleInquiry(request: Request, deps: InquiryDeps): Promise<Response> {
  if (!isSameOrigin(request)) return jsonResponse(403, { error: "forbidden" });
  const wait = deps.perClient.check(clientKey(request, deps.config.trustedClientIpHeader));
  if (wait !== null) {
    return jsonResponse(429, { error: "rate_limited" }, { "Retry-After": String(wait) });
  }
  const parsed = await readJsonBody(request);
  if (!parsed.ok) return jsonResponse(parsed.status, { error: "invalid" });
  if (isHoneypotFilled(parsed.body)) return jsonResponse(202, { status: "accepted" });
  const result = validateInquiry(parsed.body);
  if (!result.ok) return jsonResponse(400, { error: "invalid", fields: result.fields });
  const { config } = deps;
  // No default recipient: the destination is the founder's choice, and a
  // message must never go to an address nobody has confirmed receives mail.
  if (!config.resendApiKey || !config.inquiryFrom || !config.inquiryTo) {
    logEvent("inquiry_unavailable", { reason: "not_configured" });
    return jsonResponse(503, { error: "unavailable" });
  }
  const limited = deps.perEmail.check(result.value.email) ?? deps.overall.check("all");
  if (limited !== null) {
    return jsonResponse(429, { error: "rate_limited" }, { "Retry-After": String(limited) });
  }
  try {
    if (await sendThroughResend(config, result.value, deps.fetch)) {
      logEvent("inquiry_accepted", { locale: result.value.locale });
      return jsonResponse(202, { status: "accepted" });
    }
  } catch (error) {
    logEvent("inquiry_provider_failed", { reason: error instanceof Error ? error.name : "unknown" });
  }
  return jsonResponse(503, { error: "unavailable" });
}
