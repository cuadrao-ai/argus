import { expect, test } from "bun:test";
import * as recovery from "@/lib/session-recovery";

const owner = { id: "owner", is_anonymous: false };
const result = (user: typeof owner | null, error: Error | null = null) => ({ data: { user }, error });

test.each([
  ["absent check", undefined, "error"],
  ["returned failure", result(null, new Error("unavailable")), "error"],
  ["failure with stale identity", result(owner, new Error("unavailable")), "error"],
  ["settled missing", result(null), "missing"],
  ["anonymous", result({ ...owner, is_anonymous: true }), "missing"],
  ["authenticated", result(owner), "allowed"],
] as const)("identity classification: %s", async (_label, identity, outcome) => {
  expect(await recovery.classifyBusinessIdentity(async () => identity)).toBe(outcome);
});

test("a thrown check is an error, including client creation failure", async () => {
  expect(await recovery.classifyBusinessIdentity(async () => { throw new Error("unavailable"); })).toBe("error");
});

test("client access requires the expected owner", async () => {
  expect(await recovery.classifyBusinessIdentity(async () => result(owner), "owner")).toBe("allowed");
  expect(await recovery.classifyBusinessIdentity(async () => result(owner), "different-owner")).toBe("error");
  expect(await recovery.classifyBusinessIdentity(async () => result({ ...owner, is_anonymous: true }), "owner")).toBe("missing");
});
