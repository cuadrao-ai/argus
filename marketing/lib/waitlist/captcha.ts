import { PROVIDER_TIMEOUT_MS } from "../forms/config";

export async function verifyWaitlistCaptcha(
  token: string,
  secret: string,
  hostname: string,
  doFetch: typeof fetch,
): Promise<boolean> {
  if (!token || !secret || token.length > 2048) return false;
  const response = await doFetch("https://challenges.cloudflare.com/turnstile/v0/siteverify", {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({ secret, response: token }),
    signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
  });
  if (!response.ok) return false;
  const result: unknown = await response.json();
  if (!result || typeof result !== "object") return false;
  return "success" in result && result.success === true
    && "hostname" in result && result.hostname === hostname
    && "action" in result && result.action === "personal_waitlist";
}
