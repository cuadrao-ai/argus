import { createHmac, timingSafeEqual } from "node:crypto";

type Purpose = "confirm" | "leave";
const TOKEN = /^[0-9a-f]{32}\.[0-9]{1,13}\.[0-9a-f]{64}$/;
const HOURS_48 = 48 * 60 * 60 * 1000;

export function makeWaitlistToken(id: string, purpose: Purpose, issuedAt: Date): string {
  if (!/^[0-9a-f]{64}$/.test(id)) throw new Error("Invalid verification ID");
  const payload = `${id.slice(0, 32)}.${purpose === "leave" ? 0 : issuedAt.getTime()}`;
  return `${payload}.${createHmac("sha256", id).update(`${purpose}:${payload}`).digest("hex")}`;
}

export function tokenPrefix(token: string): string | null {
  return TOKEN.test(token) ? token.split(".")[0] : null;
}

export function verifyWaitlistToken(token: string, id: string, purpose: Purpose, now: Date): Date | null {
  if (!TOKEN.test(token)) return null;
  const issuedAt = new Date(Number(token.split(".")[1]));
  if (purpose === "confirm" && (issuedAt > now || now.getTime() - issuedAt.getTime() >= HOURS_48)) return null;
  const expected = makeWaitlistToken(id, purpose, issuedAt);
  if (expected.length !== token.length || !timingSafeEqual(Buffer.from(expected), Buffer.from(token))) return null;
  return issuedAt;
}
