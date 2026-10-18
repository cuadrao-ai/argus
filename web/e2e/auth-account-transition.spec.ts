import { expect, test } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { BUSINESS_PRIVACY_NOTICE_STORAGE_KEY } from "../lib/browser-storage";
import { BUSINESS_PRIVACY_NOTICE_VERSION, currentNoticeHashes } from "../lib/business-privacy-notice";
const oldId = "11111111-1111-4111-8111-111111111111";
const newId = "22222222-2222-4222-8222-222222222222";
function token(id: string) {
  const encode = (value: object) => Buffer.from(JSON.stringify(value)).toString("base64url");
  return `${encode({ alg: "HS256" })}.${encode({ sub: id, exp: Math.floor(Date.now() / 1000) + 3600 })}.test-signature`;
}
function user(id: string) { return { id, aud: "authenticated", role: "authenticated", email: `${id}@example.test`, app_metadata: {}, user_metadata: {}, created_at: "2026-10-01T00:00:00Z" }; }
for (const existingSession of [true, false]) {
test(`verified signup installs the new account with existing session ${existingSession}`, async ({ page, context, baseURL }) => {
  const events: string[] = [];
  const oldToken = token(oldId);
  const newToken = token(newId);
  if (existingSession) await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${Buffer.from(JSON.stringify({ access_token: oldToken, refresh_token: "old-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: user(oldId) })).toString("base64url")}`, url: baseURL! }]);
  await page.route("**/auth/v1/logout?**", async route => { events.push("end-old"); await route.fulfill({ status: 204 }); });
  await page.route("**/auth/v1/user", async route => { events.push("verify-new"); await route.fulfill({ json: user(newId) }); });
  await page.route("**/api/v1/auth/logout", async route => { events.push("clear-cookies"); await route.fulfill({ json: { success: true } }); });
  await page.route("**/api/v1/me", async route => { events.push(route.request().headers().authorization === `Bearer ${newToken}` ? "read-new" : "read-old"); await route.fulfill({ status: 401, json: { code: "unauthorized" } }); });
  await page.goto(`/#access_token=${newToken}&refresh_token=new-refresh&type=signup`);
  await expect.poll(() => events).toContain("read-new");
  if (existingSession) expect(events.indexOf("end-old")).toBeLessThan(events.indexOf("verify-new"));
  expect(events).not.toContain("read-old");
  await expect(page).not.toHaveURL(/access_token/);
  await page.reload();
  await expect.poll(() => events.filter(value => value === "read-new").length).toBe(2);
});

}

for (const failure of ["invalid-link", "cookie-clear-failed"]) {
  test(`${failure} never resumes the previous account`, async ({ page, context, baseURL }) => {
    const oldToken = token(oldId);
    await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${Buffer.from(JSON.stringify({ access_token: oldToken, refresh_token: "old-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: user(oldId) })).toString("base64url")}`, url: baseURL! }]);
    const reads: string[] = [];
    await page.route("**/auth/v1/logout?**", route => route.fulfill({ status: 204 }));
    await page.route("**/auth/v1/user", route => route.fulfill({ status: 401, json: { message: "Invalid token" } }));
    await page.route("**/api/v1/auth/logout", route => route.fulfill({ status: failure === "cookie-clear-failed" ? 503 : 200, json: { success: failure !== "cookie-clear-failed" } }));
    await page.route("**/api/v1/me", route => { reads.push(route.request().headers().authorization ?? "none"); return route.fulfill({ status: 401, json: { code: "unauthorized" } }); });
    await page.goto(`/#access_token=${token(newId)}&refresh_token=new-refresh&type=signup`);
    await expect(page.getByRole("alert")).toBeVisible();
    expect(reads).toEqual([]);
    await expect(page).not.toHaveURL(/access_token/);
    await page.reload();
    await expect.poll(() => reads.length).toBeGreaterThan(0);
    expect(reads).not.toContain(`Bearer ${oldToken}`);
    const cookies = await context.cookies();
    expect(cookies.some(cookie => cookie.name.startsWith("sb-127-auth-token"))).toBe(false);
  });
}

test("a fresh account drops persisted old Business context and waits for its own space", async ({ page, context, baseURL }) => {
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const session = { access_token: token(newId), refresh_token: "new-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: user(newId) };
  await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${Buffer.from(JSON.stringify(session)).toString("base64url")}`, url: baseURL! }]);
  const textSha256 = (await currentNoticeHashes()).en;
  await page.addInitScript(({ oldId, noticeKey, notice }) => {
    window.localStorage.setItem("argus:business-grant:v1", JSON.stringify({ userId: oldId, grantId: "44444444-4444-4444-8444-444444444444" }));
    window.sessionStorage.setItem(noticeKey, JSON.stringify({ [notice.userId]: notice }));
  }, {
    oldId,
    noticeKey: BUSINESS_PRIVACY_NOTICE_STORAGE_KEY,
    notice: {
      userId: newId,
      acceptedAt: "2026-10-18T12:00:00.000Z",
      noticeVersion: BUSINESS_PRIVACY_NOTICE_VERSION,
      locale: "en",
      textSha256,
    },
  });
  let started = false;
  const calls: string[] = [];
  const failures: string[] = [];
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    calls.push(path);
    if (route.request().headers()["x-business-grant"]) failures.push(`old-grant:${path}`);
    if (path === "/business/space") { started = true; return route.fulfill({ json: { id: "new-space", name: "New Business" } }); }
    if ((path.startsWith("/business/") || path === "/conversations") && !started) failures.push(`before-space:${path}`);
    if (path === "/me") return route.fulfill({ json: { user: { ...user(newId), display_name: "New Owner", username: null, language: "en", locale: "en-US", onboarding: { completed: true, stage: "completed", language_confirmed: true, primary_goal: null } }, account_kind: "registered", guest: null, public_account_access_enabled: false, capabilities: { can_create_additional_conversation: true, can_manage_conversation: true, can_manage_account: true, can_use_omnisearch: true, can_submit_feedback: true } } });
    if (path === "/business/workspace") return route.fulfill({ json: await fixture.workspace() });
    if (path === "/business/overview") return route.fulfill({ json: await fixture.overview("2026-10-01", "2026-10-31") });
    if (path === "/business/spaces") return route.fulfill({ json: { spaces: [{ space_id: "new-space", name: "New Business", grant_id: "new-owner-grant", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true }] } });
    if (path === "/business/receipts") return route.fulfill({ json: { items: [], activity: { unread_count: 0, pending_review_count: 0, reading_count: 0, needs_attention_count: 0, presentation: "none" } } });
    if (path === "/business/captures" || path === "/conversations") return route.fulfill({ json: { items: [], next_cursor: null } });
    return route.fulfill({ status: 404, json: { code: "fixture_route_unavailable" } });
  });
  await page.goto("/biz");
  await expect(page.getByText("New Business", { exact: true }).first()).toBeVisible();
  await expect.poll(() => calls.includes("/conversations") && calls.includes("/business/captures")).toBe(true);
  expect(failures).toEqual([]);
  await page.reload();
  await expect(page.getByText("New Business", { exact: true }).first()).toBeVisible();
  expect(failures).toEqual([]);
});

test("signing out of Business opens login without the account-changed alert", async ({ page, context, baseURL }) => {
  const fixture = createFixtureBusinessDataSource({ chatAvailable: true });
  const session = { access_token: token(newId), refresh_token: "new-refresh", expires_at: Math.floor(Date.now() / 1000) + 3600, token_type: "bearer", user: user(newId) };
  await context.addCookies([{ name: "sb-127-auth-token", value: `base64-${Buffer.from(JSON.stringify(session)).toString("base64url")}`, url: baseURL! }]);
  await page.route("**/auth/v1/logout?**", route => route.fulfill({ status: 204 }));
  await page.route("**/api/v1/**", async route => {
    const path = new URL(route.request().url()).pathname.replace("/api/v1", "");
    if (path === "/auth/logout") return route.fulfill({ json: { success: true } });
    if (path === "/business/space") return route.fulfill({ json: { id: "new-space", name: "New Business" } });
    if (path === "/me") return route.fulfill({ json: { user: { ...user(newId), display_name: "New Owner", username: null, language: "es", locale: "es-419", onboarding: { completed: true, stage: "completed", language_confirmed: true, primary_goal: null } }, account_kind: "registered", guest: null, public_account_access_enabled: false, capabilities: { can_create_additional_conversation: true, can_manage_conversation: true, can_manage_account: true, can_use_omnisearch: true, can_submit_feedback: true } } });
    if (path === "/business/workspace") return route.fulfill({ json: await fixture.workspace() });
    if (path === "/business/overview") return route.fulfill({ json: await fixture.overview("2026-10-01", "2026-10-31") });
    if (path === "/business/spaces") return route.fulfill({ json: { spaces: [{ space_id: "new-space", name: "New Business", grant_id: "new-owner-grant", role: "owner", capabilities: ["read", "prepare", "approve"], access_seen: true }] } });
    if (path === "/business/receipts") return route.fulfill({ json: { items: [], activity: { unread_count: 0, pending_review_count: 0, reading_count: 0, needs_attention_count: 0, presentation: "none" } } });
    if (path === "/business/captures" || path === "/conversations") return route.fulfill({ json: { items: [], next_cursor: null } });
    return route.fulfill({ status: 404, json: { code: "fixture_route_unavailable" } });
  });
  await page.goto("/biz");
  await expect(page.getByText("New Business", { exact: true }).first()).toBeVisible();
  await page.getByRole("button", { name: "Settings" }).click();
  await page.getByRole("button", { name: "Log out" }).click();
  await expect(page).toHaveURL(/\/\?auth=login/);
  await expect(page.getByText("Your account changed")).toHaveCount(0);
  await page.screenshot({
    path: "../docs/reports/evidence/business-signin-browser-check/business-sign-out-login.png",
    fullPage: true,
  });
});
