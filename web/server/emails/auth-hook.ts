import { createHash } from "node:crypto";
import { Webhook } from "standardwebhooks";
import { parseAuthMail, renderAuthMail } from "./auth-actions";

export const STAGING_AUTH_EMAIL = {
  projectRef: "skedzwocnmrhfigiwyzi",
  supabaseUrl: "https://skedzwocnmrhfigiwyzi.supabase.co",
  appOrigin: "https://cuadrao-web-staging.onrender.com",
  expirySeconds: 3600,
  renderServiceId: "srv-db5ihr7lot8c73f3b3h0",
} as const;
const MAX_BODY_BYTES = 65_536;

export type AuthEmailHookConfig = {
  enabled: boolean;
  projectRef: string;
  supabaseUrl: string;
  appOrigin: string;
  expirySeconds: number;
  renderServiceId: string;
  hookSecret: string;
};
export type AuthDelivery = {
  recipient: string;
  from: string;
  replyTo: string;
  subject: string;
  html: string;
  text: string;
  idempotencyKey: string;
};
export type AuthEmailSender = (delivery: AuthDelivery) => Promise<void>;

function error(status: number) {
  return Response.json({ error: { http_code: status, message: "Auth email unavailable" } }, { status, headers: { "Cache-Control": "no-store" } });
}

async function readBody(request: Request) {
  if (!request.body) throw new Error("Missing hook body");
  const declared = request.headers.get("content-length");
  if (declared !== null && (!/^\d+$/.test(declared) || Number(declared) > MAX_BODY_BYTES)) throw new Error("Hook body too large");
  const chunks: Uint8Array[] = [];
  let bytes = 0;
  const reader = request.body.getReader();
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      bytes += value.byteLength;
      if (bytes > MAX_BODY_BYTES) { await reader.cancel(); throw new Error("Hook body too large"); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  return Buffer.concat(chunks, bytes);
}

export async function handleAuthEmailHook(request: Request, config: AuthEmailHookConfig, send: AuthEmailSender): Promise<Response> {
  if (!config.enabled) return error(404);
  if (
    config.projectRef !== STAGING_AUTH_EMAIL.projectRef ||
    config.supabaseUrl !== STAGING_AUTH_EMAIL.supabaseUrl ||
    config.appOrigin !== STAGING_AUTH_EMAIL.appOrigin ||
    config.expirySeconds !== STAGING_AUTH_EMAIL.expirySeconds ||
    config.renderServiceId !== STAGING_AUTH_EMAIL.renderServiceId || !config.hookSecret
  ) return error(503);
  if (request.method !== "POST" || request.headers.get("content-type")?.split(";", 1)[0].trim().toLowerCase() !== "application/json") return error(400);
  const headers = {
    "webhook-id": request.headers.get("webhook-id") ?? "",
    "webhook-timestamp": request.headers.get("webhook-timestamp") ?? "",
    "webhook-signature": request.headers.get("webhook-signature") ?? "",
  };
  if (headers["webhook-id"].length > 200 || headers["webhook-timestamp"].length > 20 || headers["webhook-signature"].length > 4096) return error(400);
  let body: Buffer;
  try { body = await readBody(request); } catch { return error(413); }
  let payload: unknown;
  try {
    const secret = config.hookSecret.replace(/^v1,/, "");
    payload = new Webhook(secret).verify(body, headers);
  } catch { return error(401); }
  let deliveries: AuthDelivery[];
  try {
    const sendAttemptAt = new Date(Number.parseInt(headers["webhook-timestamp"], 10) * 1000);
    const mails = parseAuthMail(payload, config.appOrigin);
    deliveries = await Promise.all(mails.map(async (mail) => ({
      recipient: mail.recipient,
      from: "Cuadrao <no-responder@mail.cuadrao.ai>",
      replyTo: "hola@cuadrao.ai",
      ...await renderAuthMail(mail, config.appOrigin, config.expirySeconds, sendAttemptAt),
      idempotencyKey: `auth-${createHash("sha256").update(`${headers["webhook-id"]}\0${mail.action}\0${mail.recipient}`).digest("hex")}`,
    })));
  } catch { return error(400); }
  try {
    for (const delivery of deliveries) await send(delivery);
  } catch { return error(503); }
  return Response.json({}, { headers: { "Cache-Control": "no-store" } });
}

export function authEmailHookConfig(env: NodeJS.ProcessEnv): AuthEmailHookConfig {
  return {
    enabled: env.CUADRAO_AUTH_EMAIL_HOOK_ENABLED === "true",
    projectRef: env.CUADRAO_AUTH_EMAIL_PROJECT_REF ?? "",
    supabaseUrl: env.NEXT_PUBLIC_SUPABASE_URL ?? "",
    appOrigin: env.ARGUS_APP_ORIGIN ?? "",
    expirySeconds: Number(env.CUADRAO_AUTH_EMAIL_OTP_EXP_SECONDS),
    renderServiceId: env.RENDER_SERVICE_ID ?? "",
    hookSecret: env.CUADRAO_AUTH_EMAIL_HOOK_SECRET ?? "",
  };
}
