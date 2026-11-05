import { describe, expect, test } from "bun:test";
import { requireChatIdentity } from "../lib/chat-auth-ownership";

describe("chat credential ownership", () => {
  test.each([null, { user: { id: "account-b" }, access_token: "b-token" }])("rejects changed or missing authentication", (session) => {
    expect(() => requireChatIdentity(session, "account-a")).toThrow("Chat account changed");
  });
  test("accepts refreshed credentials for the same identity", () => {
    expect(requireChatIdentity({ user: { id: "account-a" }, access_token: "refreshed-token" }, "account-a")).toBe("refreshed-token");
  });
});

test("create and stream enforce ownership before network dispatch", () => {
  const result = Bun.spawnSync([process.execPath, `${import.meta.dir}/fixtures/chat-auth-ownership/transport.ts`], { cwd: `${import.meta.dir}/..` });
  expect(result.stderr.toString()).toBe("");
  expect(result.exitCode).toBe(0);
});
