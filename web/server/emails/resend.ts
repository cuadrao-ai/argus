import type { AuthDelivery, AuthEmailSender } from "./auth-hook";

export function resendAuthEmailSender(apiKey: string | undefined, doFetch: typeof fetch = fetch): AuthEmailSender {
  const deadline = Date.now() + 4000;
  return async (delivery: AuthDelivery) => {
    if (!apiKey?.trim() || Date.now() >= deadline) throw new Error("Auth email provider unavailable");
    const response = await doFetch("https://api.resend.com/emails", {
      method: "POST",
      signal: AbortSignal.timeout(Math.max(1, deadline - Date.now())),
      headers: { Authorization: `Bearer ${apiKey}`, "Content-Type": "application/json", "Idempotency-Key": delivery.idempotencyKey },
      body: JSON.stringify({ from: delivery.from, reply_to: delivery.replyTo, to: [delivery.recipient], subject: delivery.subject, html: delivery.html, text: delivery.text }),
    });
    if (!response.ok) throw new Error("Auth email provider unavailable");
  };
}
