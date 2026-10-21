import { beforeEach, expect, test } from "bun:test";
import { execFileSync } from "node:child_process";
import { removeSignup, pendingSignups, sendNotice, type OpsConfig } from "../lib/ops/signups";
import { emailDigest } from "../lib/forms/validation";
import { waitlistStore } from "../lib/waitlist/store";
import { confirmWaitlist, leaveWaitlist } from "../lib/waitlist/service";
import { makeWaitlistToken } from "../lib/waitlist/tokens";
import { CONFIG } from "./forms-support";

// Requires the two signup migrations in an owned, disposable PostgreSQL container.
const container = process.env.CUADRAO_WAITLIST_TEST_CONTAINER;
const pgTest = test.skipIf(!container);
const table = "public.cuadrao_early_access_signups";
const config: OpsConfig = { ...CONFIG, supabaseUrl: "http://fixture.local", supabaseServiceKey: "fixture", noticeFrom: null };
const literal = (value: unknown): string => value === null ? "null" : `'${String(value).replaceAll("'", "''")}'`;
const column = (name: string): string => {
  if (!/^[a-z_]+$/.test(name)) throw new Error("Invalid fixture column");
  return `"${name}"`;
};
function sql(query: string): string {
  if (!container?.startsWith("cuadrao-personal-repair-")) throw new Error("Use an owned repair container");
  return execFileSync("docker", ["exec", container, "psql", "-U", "postgres", "-At", "-v", "ON_ERROR_STOP=1", "-c", query], { encoding: "utf8" }).trim();
}
const calls: { method: string; filter: string }[] = [];
const adapter = (async (input: string | URL | Request, init: RequestInit = {}) => {
  const url = new URL(String(input));
  const method = init.method ?? "GET";
  calls.push({ method, filter: url.search });
  const body = init.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
  if (url.pathname.includes("/rpc/")) {
    const rpc = url.pathname.split("/").at(-1)!;
    if (!/^cuadrao_waitlist_(register|leave|confirm)$/.test(rpc)) throw new Error("Unexpected fixture RPC");
    const args = Object.entries(body).map(([key, value]) => `${column(key)} => ${literal(value)}`).join(",");
    return Response.json(JSON.parse(sql(`select coalesce(json_agg(t),'[]') from public.${rpc}(${args}) t`)));
  }
  if (url.pathname !== "/rest/v1/cuadrao_early_access_signups") throw new Error("Unexpected fixture target");
  const filters: string[] = [];
  for (const [key, value] of url.searchParams) {
    if (["select", "limit", "order", "offset", "on_conflict"].includes(key)) continue;
    const field = column(key);
    if (value === "is.null") filters.push(`${field} is null`);
    else if (value === "not.is.null") filters.push(`${field} is not null`);
    else if (value.startsWith("eq.")) filters.push(`${field} = ${literal(value.slice(3))}`);
    else if (value.startsWith("like.")) filters.push(`${field} like ${literal(value.slice(5).replaceAll("*", "%"))}`);
    else throw new Error("Unexpected fixture filter");
  }
  const where = filters.length ? `where ${filters.join(" and ")}` : "";
  let statement: string;
  if (method === "GET") statement = `select * from ${table} ${where}`;
  else if (method === "DELETE") statement = `delete from ${table} ${where} returning *`;
  else if (method === "PATCH") statement = `update ${table} set ${Object.entries(body).map(([key, value]) => `${column(key)}=${literal(value)}`).join(",")} ${where} returning *`;
  else if (method === "POST") statement = `insert into ${table} (${Object.keys(body).map(column).join(",")}) values (${Object.values(body).map(literal).join(",")}) on conflict do nothing returning *`;
  else throw new Error("Unexpected fixture method");
  return Response.json(JSON.parse(sql(`with result as (${statement}) select coalesce(json_agg(result),'[]') from result`)));
}) as typeof fetch;
const store = waitlistStore({ supabaseUrl: config.supabaseUrl!, supabaseServiceKey: config.supabaseServiceKey! }, adapter);
const now = () => new Date();
const count = (email: string) => Number(sql(`select count(*) from ${table} where email_digest=${literal(emailDigest(email))}`));
async function register(email = "remove@example.test") {
  const row = await store.register({ email, expenseMethod: "No los llevo", wish: "Private answer" });
  expect(row?.email).toBe(email);
  return row!;
}
beforeEach(() => {
  if (!container) return;
  sql(`truncate ${table}`);
  calls.length = 0;
});

pgTest("operator removal deletes the whole DOI row and repeat does not recreate a digest", async () => {
  const row = await register();
  const token = makeWaitlistToken(row.verification_id, "leave", now());
  expect(count(row.email)).toBe(1);
  expect(await removeSignup(config, row.email, adapter)).toBe("removed");
  expect(count(row.email)).toBe(0);
  expect(await removeSignup(config, row.email, adapter)).toBe("absent");
  expect(count(row.email)).toBe(0);
  expect(await leaveWaitlist(token, { store, now })).toBe(true);
  expect(count(row.email)).toBe(0);
  expect(calls.some((call) => call.method === "POST" && call.filter.includes("on_conflict"))).toBe(false);
});

pgTest("a valid leave deletes a previously soft-removed DOI row but invalid tokens cannot", async () => {
  const row = await register();
  sql(`update ${table} set email=null,removed_at=now() where email_digest=${literal(row.email_digest)}`);
  const forged = makeWaitlistToken(row.verification_id.slice(0, 32) + "f".repeat(32), "leave", now());
  expect(await leaveWaitlist(forged, { store, now })).toBe(false);
  expect(count(row.email)).toBe(1);
  expect(await confirmWaitlist(makeWaitlistToken(row.verification_id, "confirm", now()), { store, now, send: async () => { throw new Error("No mail allowed"); } })).toBe(false);
  const token = makeWaitlistToken(row.verification_id, "leave", now());
  expect(await leaveWaitlist(token, { store, now })).toBe(true);
  expect(count(row.email)).toBe(0);
  expect(await leaveWaitlist(token, { store, now })).toBe(true);
  expect(count(row.email)).toBe(0);
});

pgTest("operator removal also deletes already soft-removed DOI rows", async () => {
  const row = await register();
  sql(`update ${table} set email=null,removed_at=now() where email_digest=${literal(row.email_digest)}`);
  expect(await removeSignup(config, row.email, adapter)).toBe("removed");
  expect(count(row.email)).toBe(0);
});

pgTest("leaving one row preserves other signups and legacy suppression", async () => {
  const row = await register();
  const other = await register("other@example.test");
  const legacy = "legacy@example.test";
  sql(`insert into ${table}(email_digest,email,language,consent_version,source) values(${literal(emailDigest(legacy))},${literal(legacy)},'es','old-policy','personal-page')`);
  expect(await removeSignup(config, legacy, adapter)).toBe("removed");
  expect(sql(`select email is null and removed_at is not null and privacy_policy_version is null from ${table} where email_digest=${literal(emailDigest(legacy))}`)).toBe("t");
  expect(await leaveWaitlist(makeWaitlistToken(row.verification_id, "leave", now()), { store, now })).toBe(true);
  expect(count(row.email)).toBe(0);
  expect(count(other.email)).toBe(1);
  expect(count(legacy)).toBe(1);
  expect(await pendingSignups(config, adapter)).toEqual([]);
  const result = await sendNotice(config, { id: "fixture", subject: { es: "Hola", en: "Hello" }, text: { es: "Fixture", en: "Fixture" } }, { recipients: [{ email: other.email, email_digest: other.email_digest, language: "es" }], stamp: true }, adapter);
  expect(result.sent).toBe(0);
  expect(result.skipped).toBe(1);
});
