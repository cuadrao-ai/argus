// Stands in for Resend and the Supabase REST API during browser tests. It keeps
// what it receives so a test can prove a message or a row actually arrived, and
// it can be switched into a failing mode to exercise the retry paths.
import { createServer } from "node:http";
import { createHash } from "node:crypto";

const PORT = Number(process.env.MOCK_PROVIDER_PORT ?? 4510);
const RESEND_KEY = "test-resend-key";
const SERVICE_KEY = "test-service-key";

const state = { emails: [], signups: new Map(), idempotent: new Map() };
const mode = { resend: "up", supabase: "up", resendDelayMs: 0 };

function readBody(request) {
  return new Promise((resolve) => {
    const chunks = [];
    request.on("data", (chunk) => chunks.push(chunk));
    request.on("end", () => resolve(Buffer.concat(chunks).toString("utf8")));
  });
}

function send(response, status, body) {
  response.writeHead(status, { "Content-Type": "application/json" });
  response.end(body === undefined ? "" : JSON.stringify(body));
}

createServer(async (request, response) => {
  const url = new URL(request.url ?? "/", `http://127.0.0.1:${PORT}`);
  const raw = request.method === "POST" || request.method === "PATCH" ? await readBody(request) : "";

  if (url.pathname === "/__state") {
    return send(response, 200, {
      emails: state.emails,
      signups: [...state.signups.values()],
    });
  }
  if (url.pathname === "/__reset") {
    state.emails = [];
    state.signups = new Map();
    state.idempotent = new Map();
    mode.resend = "up";
    mode.supabase = "up";
    mode.resendDelayMs = 0;
    return send(response, 200, { ok: true });
  }
  if (url.pathname === "/__mode") {
    Object.assign(mode, JSON.parse(raw));
    return send(response, 200, mode);
  }

  if (url.pathname === "/emails" && request.method === "POST") {
    if (request.headers.authorization !== `Bearer ${RESEND_KEY}`) return send(response, 401, { message: "bad key" });
    if (mode.resendDelayMs) await new Promise((resolve) => setTimeout(resolve, mode.resendDelayMs));
    if (mode.resend === "down") return send(response, 500, { message: "provider down" });
    const key = request.headers["idempotency-key"];
    if (key && state.idempotent.has(key)) return send(response, 200, state.idempotent.get(key));
    const email = { ...JSON.parse(raw), idempotencyKey: key };
    state.emails.push(email);
    const result = { id: `email-${state.emails.length}` };
    if (key) state.idempotent.set(key, result);
    return send(response, 200, result);
  }

  if (url.pathname.startsWith("/rest/v1/rpc/cuadrao_waitlist_")) {
    if (request.headers.apikey !== SERVICE_KEY) return send(response, 401, { message: "bad key" });
    if (mode.supabase === "down") return send(response, 503, { message: "database down" });
    const args = JSON.parse(raw);
    const name = url.pathname.split("cuadrao_waitlist_")[1];
    if (name === "register") {
      const digest = createHash("sha256").update(args.p_email).digest("hex");
      if (state.signups.has(digest)) return send(response, 200, []);
      const row = { email_digest: digest, email: args.p_email, language: "es", consent_version: args.p_privacy_policy_version, privacy_policy_version: args.p_privacy_policy_version, expense_method: args.p_expense_method, wish: args.p_wish, verification_id: args.p_verification_id, created_at: new Date().toISOString(), last_confirmation_sent_at: new Date().toISOString(), confirmed_at: null, reminder_sent_at: null };
      state.signups.set(digest, row);
      return send(response, 200, [row]);
    }
    const row = [...state.signups.values()].find((item) => item.verification_id === args.p_verification_id);
    if (name === "confirm") {
      if (!row) return send(response, 200, []);
      row.confirmed_at ??= new Date().toISOString();
      return send(response, 200, [row]);
    }
    if (name === "leave") { if (row) state.signups.delete(row.email_digest); return send(response, 200, null); }
  }
  if (url.pathname === "/rest/v1/cuadrao_early_access_signups" && request.method === "GET") {
    if (request.headers.apikey !== SERVICE_KEY) return send(response, 401, { message: "bad key" });
    const prefix = url.searchParams.get("verification_id")?.replace(/^like\./, "").replace(/\*$/, "");
    return send(response, 200, [...state.signups.values()].filter((row) => row.verification_id?.startsWith(prefix)));
  }

  if (url.pathname === "/rest/v1/cuadrao_early_access_signups" && request.method === "POST") {
    if (request.headers.apikey !== SERVICE_KEY) return send(response, 401, { message: "bad key" });
    if (mode.supabase === "down") return send(response, 503, { message: "database down" });
    const row = JSON.parse(raw);
    if (!state.signups.has(row.email_digest)) state.signups.set(row.email_digest, row);
    response.writeHead(201);
    return response.end();
  }

  return send(response, 404, { message: "not found" });
}).listen(PORT, "127.0.0.1", () => console.log(`mock providers on ${PORT}`));
