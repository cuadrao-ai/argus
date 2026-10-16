import { renderAccountEmail } from "../email/account-layout.ts";
import { PROVIDER_TIMEOUT_MS } from "../forms/config.ts";
import { unsubscribeHeaders, WAITLIST_EMAILS, type AutomaticWaitlistEmail } from "./email-content.ts";
import { makeWaitlistToken } from "./tokens.ts";
import type { WaitlistRow } from "./types.ts";

export type WaitlistMailConfig = {
  apiKey: string;
  apiUrl: string;
  from: string;
  origin: string;
  postalAddress: string;
};

export type MailOutcome = "sent" | "refused" | "unknown";

export function waitlistMail(config: WaitlistMailConfig, doFetch: typeof fetch) {
  return async (kind: AutomaticWaitlistEmail, row: WaitlistRow): Promise<MailOutcome> => {
    const copy = WAITLIST_EMAILS[kind];
    const sentAt = kind === "welcome" ? row.confirmed_at : row.last_confirmation_sent_at;
    if (!sentAt) throw new Error("Missing delivery reservation");
    const timestamp = new Date(sentAt);
    const leave = new URL("/api/waitlist/leave", config.origin);
    leave.searchParams.set("token", makeWaitlistToken(row.verification_id, "leave", timestamp));
    const confirm = new URL("/api/waitlist/confirm", config.origin);
    confirm.searchParams.set("token", makeWaitlistToken(row.verification_id, "confirm", timestamp));
    const rendered = renderAccountEmail({
      title: copy.subject,
      paragraphs: copy.paragraphs,
      ...("button" in copy ? { action: { label: copy.button, url: confirm.toString() }, expiryNote: copy.expiryNote, afterAction: copy.afterAction } : {}),
      unsubscribeUrl: leave.toString(),
      postalAddress: config.postalAddress,
    });
    const body = JSON.stringify({ from: config.from, to: [row.email], reply_to: "hola@cuadrao.ai", subject: copy.subject, html: rendered.html, text: rendered.text, headers: unsubscribeHeaders(leave.toString()) });
    // A lost response gets one retry with exactly the same provider key and body.
    let uncertain = false;
    for (let attempt = 0; attempt < 2; attempt += 1) {
      try {
        const response = await doFetch(`${config.apiUrl}/emails`, {
          method: "POST",
          headers: { Authorization: `Bearer ${config.apiKey}`, "Content-Type": "application/json", "Idempotency-Key": `waitlist-${kind}-${row.verification_id.slice(0, 32)}-${timestamp.getTime()}` },
          body,
          signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
        });
        if (response.ok) return "sent";
        if (response.status >= 400 && response.status < 500 && response.status !== 409 && response.status !== 429) return uncertain ? "unknown" : "refused";
        uncertain = true;
      } catch { uncertain = true; }
    }
    return "unknown";
  };
}
