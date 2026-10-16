import { readFormsConfig } from "../forms/config";
import { parseMailbox } from "../forms/validation";
import { WindowLimiter } from "../forms/rate-limit";
import { waitlistMail } from "./email";
import { waitlistStore } from "./store";
import type { WaitlistDeps } from "./service";

const perClient = new WindowLimiter(5, 60 * 60 * 1000);

export function waitlistDeps(env: Record<string, string | undefined> = process.env): WaitlistDeps | null {
  const config = readFormsConfig(env);
  const from = env.MARKETING_WAITLIST_FROM?.trim();
  const postalAddress = env.MARKETING_POSTAL_ADDRESS?.trim();
  const origin = env.CUADRAO_WAITLIST_ORIGIN?.trim();
  const captchaSecret = env.CUADRAO_WAITLIST_TURNSTILE_SECRET?.trim();
  if (!config.supabaseUrl || !config.supabaseServiceKey || !config.resendApiKey || !from || !postalAddress || !origin || !captchaSecret) return null;
  const mailbox = parseMailbox(/^Cuadrao <([^<>\r\n]+)>$/.exec(from)?.[1]);
  if (!mailbox?.endsWith("@cuadrao.ai") || !/^Cuadrao\s*</.test(from)) return null;
  let url: URL;
  try { url = new URL(origin); } catch { return null; }
  if (url.protocol !== "https:" || url.username || url.password || url.pathname !== "/" || url.search || url.hash) return null;
  return {
    store: waitlistStore({ supabaseUrl: config.supabaseUrl, supabaseServiceKey: config.supabaseServiceKey }, fetch),
    send: waitlistMail({ apiKey: config.resendApiKey, apiUrl: config.resendApiUrl, from, postalAddress, origin: url.origin }, fetch),
    fetch,
    captchaSecret,
    hostname: url.hostname,
    perClient,
    trustedClientIpHeader: config.trustedClientIpHeader,
    now: () => new Date(),
  };
}
