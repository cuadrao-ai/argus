import { verifyWaitlistCaptcha } from "./captcha";
import { tokenPrefix, verifyWaitlistToken } from "./tokens";
import type { WaitlistRow, WaitlistStore } from "./types";
import type { MailOutcome } from "./email";
import type { AutomaticWaitlistEmail } from "./email-content";
import { parsePersonalWaitlist } from "../forms/personal-waitlist-input";
import { clientKey, isSameOrigin, jsonResponse, logEvent, readJsonBody } from "../forms/http";
import { isHoneypotFilled } from "../forms/validation";
import type { WindowLimiter } from "../forms/rate-limit";

export type WaitlistDeps = {
  store: WaitlistStore;
  send: (kind: AutomaticWaitlistEmail, row: WaitlistRow) => Promise<MailOutcome>;
  fetch: typeof fetch;
  captchaSecret: string;
  hostname: string;
  perClient: WindowLimiter;
  trustedClientIpHeader: string | null;
  now: () => Date;
};

export async function handleWaitlistSignup(request: Request, deps: WaitlistDeps): Promise<Response> {
  if (!isSameOrigin(request)) return jsonResponse(403, { error: "forbidden" });
  const wait = deps.perClient.check(clientKey(request, deps.trustedClientIpHeader));
  if (wait !== null) return jsonResponse(429, { error: "rate_limited" }, { "Retry-After": String(wait) });
  const parsed = await readJsonBody(request);
  if (!parsed.ok) return jsonResponse(parsed.status, { error: "invalid" });
  if (isHoneypotFilled(parsed.body)) return jsonResponse(200, { status: "registered" });
  const input = parsePersonalWaitlist(parsed.body);
  if (!input) return jsonResponse(400, { error: "invalid" });
  try {
    if (!await verifyWaitlistCaptcha(input.captchaToken, deps.captchaSecret, deps.hostname, deps.fetch)) return jsonResponse(400, { error: "invalid" });
    const row = await deps.store.register({ email: input.email, expenseMethod: input.expenseMethod, wish: input.wish });
    if (row) {
      const outcome = await deps.send("confirmation", row);
      if (outcome !== "sent") {
        if (outcome === "refused") await deps.store.release(row.verification_id, row.last_confirmation_sent_at!, false);
        logEvent("waitlist_delivery_failed", { kind: "confirmation", outcome });
        return jsonResponse(503, { error: "unavailable" });
      }
    }
    logEvent("waitlist_signup_accepted");
    return jsonResponse(200, { status: "registered" });
  } catch {
    logEvent("waitlist_signup_failed");
    return jsonResponse(503, { error: "unavailable" });
  }
}

export async function confirmWaitlist(token: string, deps: Pick<WaitlistDeps, "store" | "send" | "now">): Promise<boolean> {
  const prefix = tokenPrefix(token);
  if (!prefix) return false;
  const row = await deps.store.find(prefix);
  if (!row) return false;
  const issued = verifyWaitlistToken(token, row.verification_id, "confirm", deps.now());
  if (!issued) return false;
  const confirmed = await deps.store.confirm(row.verification_id, issued.toISOString());
  if (!confirmed?.confirmed_at) return false;
  // Repeated clicks can recover a lost welcome response inside the provider's
  // idempotency window, then only show the saved confirmation.
  if (deps.now().getTime() - new Date(confirmed.confirmed_at).getTime() < 10 * 60 * 1000) {
    const outcome = await deps.send("welcome", confirmed);
    if (outcome !== "sent") logEvent("waitlist_delivery_failed", { kind: "welcome", outcome });
  }
  return true;
}

export async function leaveWaitlist(token: string, deps: Pick<WaitlistDeps, "store" | "now">): Promise<boolean> {
  const prefix = tokenPrefix(token);
  if (!prefix) return false;
  const row = await deps.store.find(prefix, "deletion");
  if (!row) return true;
  if (!verifyWaitlistToken(token, row.verification_id, "leave", deps.now())) return false;
  await deps.store.leave(row.verification_id);
  logEvent("waitlist_left");
  return true;
}

export async function maintainWaitlist(deps: Pick<WaitlistDeps, "store" | "send">) {
  const purged = await deps.store.purge();
  const rows = await deps.store.reminders();
  let sent = 0;
  let failed = 0;
  for (const row of rows) {
    // Read again so a confirmed or deleted row does not get a queued reminder.
    const active = await deps.store.find(row.verification_id.slice(0, 32));
    if (!active || active.confirmed_at) continue;
    const outcome = await deps.send("reminder", row);
    if (outcome === "sent") sent += 1;
    else {
      failed += 1;
      if (outcome === "refused") await deps.store.release(row.verification_id, row.last_confirmation_sent_at!, true);
    }
  }
  const result = { purged, remindersSent: sent, remindersFailed: failed };
  logEvent("waitlist_maintenance", result);
  return result;
}
