import { PROVIDER_TIMEOUT_MS, SIGNUP_CONSENT_VERSION, type FormsConfig } from "./config";
import { clientKey, isSameOrigin, jsonResponse, logEvent, readJsonBody } from "./http";
import { WindowLimiter } from "./rate-limit";
import { emailDigest, isHoneypotFilled, validateSignup, type SignupInput } from "./validation";

export type SignupDeps = {
  config: FormsConfig;
  fetch: typeof fetch;
  perClient: WindowLimiter;
  overall: WindowLimiter;
};

export const SIGNUP_TABLE = "cuadrao_early_access_signups";

// The digest is the primary key. A repeat address, and an address that was
// removed, both conflict and are ignored, so the answer never reveals which.
async function storeSignup(
  config: FormsConfig,
  input: SignupInput,
  doFetch: typeof fetch,
): Promise<boolean> {
  const response = await doFetch(
    `${config.supabaseUrl}/rest/v1/${SIGNUP_TABLE}?on_conflict=email_digest`,
    {
      method: "POST",
      headers: {
        apikey: config.supabaseServiceKey ?? "",
        Authorization: `Bearer ${config.supabaseServiceKey}`,
        "Content-Type": "application/json",
        Prefer: "resolution=ignore-duplicates,return=minimal",
      },
      body: JSON.stringify({
        email_digest: emailDigest(input.email),
        email: input.email,
        language: input.locale,
        consent_version: SIGNUP_CONSENT_VERSION,
        source: "personal-page",
      }),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    },
  );
  if (!response.ok) logEvent("signup_store_rejected", { status: response.status });
  return response.ok;
}

export async function handleSignup(request: Request, deps: SignupDeps): Promise<Response> {
  if (!isSameOrigin(request)) return jsonResponse(403, { error: "forbidden" });
  const wait = deps.perClient.check(clientKey(request, deps.config.trustedClientIpHeader));
  if (wait !== null) {
    return jsonResponse(429, { error: "rate_limited" }, { "Retry-After": String(wait) });
  }
  const parsed = await readJsonBody(request);
  if (!parsed.ok) return jsonResponse(parsed.status, { error: "invalid" });
  if (isHoneypotFilled(parsed.body)) return jsonResponse(200, { status: "registered" });
  const result = validateSignup(parsed.body);
  if (!result.ok) return jsonResponse(400, { error: "invalid", fields: result.fields });
  // Only a valid signup spends the shared allowance, so junk cannot exhaust it.
  const overall = deps.overall.check("all");
  if (overall !== null) {
    return jsonResponse(429, { error: "rate_limited" }, { "Retry-After": String(overall) });
  }
  const { config } = deps;
  if (!config.supabaseUrl || !config.supabaseServiceKey) {
    logEvent("signup_unavailable", { reason: "not_configured" });
    return jsonResponse(503, { error: "unavailable" });
  }
  try {
    if (await storeSignup(config, result.value, deps.fetch)) {
      logEvent("signup_stored", { locale: result.value.locale });
      return jsonResponse(200, { status: "registered" });
    }
  } catch (error) {
    logEvent("signup_store_failed", { reason: error instanceof Error ? error.name : "unknown" });
  }
  return jsonResponse(503, { error: "unavailable" });
}
