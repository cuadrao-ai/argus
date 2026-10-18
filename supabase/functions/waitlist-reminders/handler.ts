import { createHash, timingSafeEqual } from "node:crypto";
import { waitlistMail } from "../../../marketing/lib/waitlist/email.ts";
import { waitlistStore } from "../../../marketing/lib/waitlist/store.ts";
import { remindWaitlist } from "../../../marketing/lib/waitlist/reminders.ts";
import { parseMailbox } from "../../../marketing/lib/forms/validation.ts";

export const STAGING_URL = "https://skedzwocnmrhfigiwyzi.supabase.co";
type Env = Record<string, string | undefined>;

export async function handleReminderRequest(request: Request, env: Env, doFetch: typeof fetch = fetch): Promise<Response> {
  if (request.method !== "POST") return Response.json({ error: "method_not_allowed" }, { status: 405 });
  const key = env.SUPABASE_SERVICE_ROLE_KEY?.trim();
  const schedulerKey = env.CUADRAO_WAITLIST_SCHEDULER_KEY?.trim();
  if (env.SUPABASE_URL !== STAGING_URL || !key || !schedulerKey || schedulerKey === key) return Response.json({ error: "unavailable" }, { status: 503 });
  const supplied = createHash("sha256").update(request.headers.get("x-cuadrao-waitlist-scheduler-key") ?? "").digest();
  const expected = createHash("sha256").update(schedulerKey).digest();
  if (!timingSafeEqual(supplied, expected)) {
    return Response.json({ error: "unauthorized" }, { status: 401 });
  }
  try {
    const from = env.MARKETING_WAITLIST_FROM?.trim();
    const postalAddress = env.MARKETING_POSTAL_ADDRESS?.trim();
    const apiKey = env.RESEND_API_KEY?.trim();
    const mailbox = parseMailbox(/^Cuadrao <([^<>\r\n]+)>$/.exec(from ?? "")?.[1]);
    const origin = new URL(env.CUADRAO_WAITLIST_ORIGIN ?? "");
    if (!from || (!mailbox?.endsWith("@cuadrao.ai") && mailbox !== "no-responder@mail.cuadrao.ai") || !postalAddress || !apiKey || origin.protocol !== "https:" || origin.username || origin.password || origin.pathname !== "/" || origin.search || origin.hash) throw new Error("Missing delivery configuration");
    const store = waitlistStore({ supabaseUrl: STAGING_URL, supabaseServiceKey: key }, doFetch);
    const send = waitlistMail({ apiKey, apiUrl: "https://api.resend.com", from, postalAddress, origin: origin.origin }, doFetch);
    const result = await remindWaitlist({ store, send }, 2);
    console.info(JSON.stringify({ event: "waitlist_reminders", ...result }));
    return Response.json(result, { status: result.remindersFailed ? 503 : 200 });
  } catch {
    console.error(JSON.stringify({ event: "waitlist_reminders_failed" }));
    return Response.json({ error: "unavailable" }, { status: 503 });
  }
}
