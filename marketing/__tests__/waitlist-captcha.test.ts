import { expect, test } from "bun:test";
import { verifyWaitlistCaptcha } from "../lib/waitlist/captcha";

test("waitlist captcha requires a successful token for this hostname and action", async () => {
  for (const result of [
    { success: false, hostname: "cuadrao.example.test", action: "personal_waitlist" },
    { success: true, hostname: "other.example.test", action: "personal_waitlist" },
    { success: true, hostname: "cuadrao.example.test", action: "signup" },
    { success: true },
    null,
  ]) {
    const doFetch = (async () => Response.json(result)) as typeof fetch;
    expect(await verifyWaitlistCaptcha("token", "test-secret", "cuadrao.example.test", doFetch)).toBe(false);
  }
  const doFetch = (async (_url: unknown, init: RequestInit) => {
    expect(String(init.body)).toBe("secret=test-secret&response=token");
    return Response.json({ success: true, hostname: "cuadrao.example.test", action: "personal_waitlist" });
  }) as typeof fetch;
  expect(await verifyWaitlistCaptcha("token", "test-secret", "cuadrao.example.test", doFetch)).toBe(true);
});

test("missing credentials never bypass captcha", async () => {
  const doFetch = (async () => { throw new Error("must not call provider"); }) as typeof fetch;
  expect(await verifyWaitlistCaptcha("", "test-secret", "cuadrao.example.test", doFetch)).toBe(false);
  expect(await verifyWaitlistCaptcha("token", "", "cuadrao.example.test", doFetch)).toBe(false);
});
