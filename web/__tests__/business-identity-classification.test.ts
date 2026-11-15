import { expect, test } from "bun:test";
import * as recovery from "@/lib/session-recovery";
import { AuthSessionMissingError } from "@supabase/supabase-js";

const owner = { id: "owner", is_anonymous: false };
const result = (user: typeof owner | null, error: Error | null = null) => ({ data: { user }, error });

test.each([
  ["absent check", undefined, "error"],
  ["returned failure", result(null, new Error("unavailable")), "error"],
  ["failure with stale identity", result(owner, new Error("unavailable")), "error"],
  ["settled missing", result(null), "missing"],
  ["missing session error", result(null, new AuthSessionMissingError()), "missing"],
  ["anonymous", result({ ...owner, is_anonymous: true }), "missing"],
  ["authenticated", result(owner), "allowed"],
] as const)("identity classification: %s", async (_label, identity, outcome) => {
  expect(await recovery.classifyBusinessIdentity(async () => identity)).toBe(outcome);
});

test("a thrown check is an error, including client creation failure", async () => {
  expect(await recovery.classifyBusinessIdentity(async () => { throw new Error("unavailable"); })).toBe("error");
});

test("a thrown missing-session error still confirms missing identity", async () => {
  expect(await recovery.classifyBusinessIdentity(async () => { throw new AuthSessionMissingError(); })).toBe("missing");
});

test("an ordinary error named like missing session remains a failure", async () => {
  const error = new Error("unavailable");
  error.name = "AuthSessionMissingError";
  expect(await recovery.classifyBusinessIdentity(async () => result(null, error))).toBe("error");
});

test("client access requires the expected owner", async () => {
  expect(await recovery.classifyBusinessIdentity(async () => result(owner), "owner")).toBe("allowed");
  expect(await recovery.classifyBusinessIdentity(async () => result(owner), "different-owner")).toBe("error");
  expect(await recovery.classifyBusinessIdentity(async () => result({ ...owner, is_anonymous: true }), "owner")).toBe("missing");
});
