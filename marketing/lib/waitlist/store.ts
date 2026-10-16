import { randomBytes } from "node:crypto";
import { PROVIDER_TIMEOUT_MS } from "../forms/config";
import type { WaitlistRow, WaitlistStore } from "./types";

export const PRIVACY_POLICY_VERSION = "2026-10-16";
export type WaitlistDatabaseConfig = { supabaseUrl: string; supabaseServiceKey: string };

export function waitlistStore(config: WaitlistDatabaseConfig, doFetch: typeof fetch): WaitlistStore {
  async function request(path: string, body?: Record<string, unknown>): Promise<unknown> {
    const response = await doFetch(`${config.supabaseUrl}/rest/v1/${path}`, {
      method: body ? "POST" : "GET",
      headers: { apikey: config.supabaseServiceKey, Authorization: `Bearer ${config.supabaseServiceKey}`, "Content-Type": "application/json" },
      ...(body ? { body: JSON.stringify(body) } : {}),
      signal: AbortSignal.timeout(PROVIDER_TIMEOUT_MS),
    });
    if (!response.ok) throw new Error(`Waitlist database HTTP ${response.status}`);
    const text = await response.text();
    return text ? JSON.parse(text) : null;
  }
  const rows = async (name: string, body: Record<string, unknown>) => (await request(`rpc/cuadrao_waitlist_${name}`, body)) as WaitlistRow[];
  return {
    async register(input) {
      return (await rows("register", { p_email: input.email, p_expense_method: input.expenseMethod, p_wish: input.wish, p_verification_id: randomBytes(32).toString("hex"), p_privacy_policy_version: PRIVACY_POLICY_VERSION }))[0] ?? null;
    },
    async find(prefix) {
      if (!/^[0-9a-f]{32}$/.test(prefix)) return null;
      const found = await request(`cuadrao_early_access_signups?verification_id=like.${prefix}*&privacy_policy_version=not.is.null&removed_at=is.null&limit=1`) as WaitlistRow[];
      return found[0] ?? null;
    },
    async confirm(id, issuedAt) { return (await rows("confirm", { p_verification_id: id, p_issued_at: issuedAt }))[0] ?? null; },
    async leave(id) { await request("rpc/cuadrao_waitlist_leave", { p_verification_id: id }); },
    async release(id, reservedAt, reminder) { await request("rpc/cuadrao_waitlist_release", { p_verification_id: id, p_reserved_at: reservedAt, p_reminder: reminder }); },
    async reminders() { return rows("reminders", { p_limit: 100 }); },
    async purge() { return Number(await request("rpc/cuadrao_waitlist_purge", { p_limit: 100 })); },
  };
}
