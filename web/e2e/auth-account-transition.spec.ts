import { expect, test } from "@playwright/test";
const oldId = "11111111-1111-4111-8111-111111111111";
const newId = "22222222-2222-4222-8222-222222222222";
function token(id: string) {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256" })}.${encode({ sub: id, exp: Math.floor(Date.now() / 1000) + 3600 })}.synthetic`;
}
function user(id: string) { return { id, aud: "authenticated", role: "authenticated", email: `${id}@example.test`, app_metadata: {}, user_metadata: {}, created_at: "2026-10-01T00:00:00Z" }; }
test("a verified signup replaces the old browser session before reading the account", async ({ page, context, baseURL }) => {
  const events: string[] = [];
  const oldToken = token(oldId);
  const newToken = token(newId);
  await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${Buffer.from(JSON.stringify({ access_token: oldToken, refresh_token: "old-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: user(oldId) })).toString("base64url")}`, url: baseURL! }]);
  await page.route("**/auth/v1/logout?**", async route => { events.push("end-old"); await route.fulfill({ status: 204 }); });
  await page.route("**/auth/v1/user", async route => { events.push("verify-new"); await route.fulfill({ json: user(newId) }); });
  await page.route("**/api/v1/auth/logout", async route => { events.push("clear-cookies"); await route.fulfill({ json: { success: true } }); });
  await page.route("**/api/v1/me", async route => { events.push(route.request().headers().authorization === `Bearer ${newToken}` ? "read-new" : "read-old"); await route.fulfill({ status: 401, json: { code: "unauthorized" } }); });
  await page.goto(`/#access_token=${newToken}&refresh_token=new-refresh&type=signup`);
  await expect.poll(() => events).toContain("read-new");
  expect(events.indexOf("end-old")).toBeLessThan(events.indexOf("verify-new"));
  expect(events).not.toContain("read-old");
  await expect(page).not.toHaveURL(/access_token/);
  await page.reload();
  await expect.poll(() => events.filter(value => value === "read-new").length).toBe(2);
});
