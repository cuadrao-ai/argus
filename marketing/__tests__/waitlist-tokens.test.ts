import { expect, test } from "bun:test";
import { makeWaitlistToken, tokenPrefix, verifyWaitlistToken } from "../lib/waitlist/tokens";
const id = "ab".repeat(32);
const start = new Date("2026-10-16T12:00:00Z");

test("confirmation is signed, purpose-bound and expires at exactly 48 hours", () => {
  const token = makeWaitlistToken(id, "confirm", start);
  expect(token).not.toContain(id);
  expect(tokenPrefix(token)).toBe(id.slice(0, 32));
  expect(verifyWaitlistToken(token, id, "confirm", new Date("2026-10-18T11:59:59.999Z"))).toEqual(start);
  expect(verifyWaitlistToken(token, id, "confirm", new Date("2026-10-18T12:00:00Z"))).toBeNull();
  expect(verifyWaitlistToken(token, id, "leave", start)).toBeNull();
  expect(verifyWaitlistToken(token, "cd".repeat(32), "confirm", start)).toBeNull();
  expect(verifyWaitlistToken(token.replace(String(start.getTime()), String(start.getTime() + 1000)), id, "confirm", start)).toBeNull();
});

test("leave remains usable beyond 30 days without exposing the signing secret", () => {
  const token = makeWaitlistToken(id, "leave", start);
  expect(verifyWaitlistToken(token, id, "leave", new Date("2027-10-16T12:00:00Z"))).not.toBeNull();
  expect(verifyWaitlistToken(`${token.slice(0,-1)}0`, id, "leave", start)).toBeNull();
  expect(tokenPrefix("bad")).toBeNull();
});
