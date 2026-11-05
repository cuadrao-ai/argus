import { expect, test, type Page } from "@playwright/test";

async function prepare(page: Page, outcome: "token" | "error" | "pending", native = true) {
  const requests: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.startsWith("/api/")) requests.push(request.url());
  });
  await page.route("https://**/*", async (route) => {
    const url = route.request().url();
    requests.push(url);
    if (url.startsWith("https://challenges.cloudflare.com/turnstile/v0/api.js?")) {
      await route.fulfill({
        contentType: "application/javascript",
        body: `window.turnstile = {
          render(container, options) {
            window.syntheticCaptcha = options;
            if (${JSON.stringify(outcome)} === "token") queueMicrotask(() => options.callback("synthetic-native-token"));
            if (${JSON.stringify(outcome)} === "error") queueMicrotask(() => options["error-callback"]());
            return "synthetic-widget";
          },
          remove() {}
        };`,
      });
    } else {
      await route.abort();
    }
  });
  await page.addInitScript((hasNativeHandler) => {
    Object.assign(window, { nativeMessages: [] });
    if (hasNativeHandler) {
      Object.assign(window, { webkit: { messageHandlers: { argusCaptcha: {
        postMessage(message: unknown) {
          (window as unknown as { nativeMessages: unknown[] }).nativeMessages.push(message);
        },
      } } } });
    }
  }, native);
  return requests;
}

for (const outcome of ["token", "error"] as const) {
  test(`the exact native document returns ${outcome} without auth or session requests`, async ({ page }) => {
    const requests = await prepare(page, outcome);
    const response = await page.goto("/auth/native-captcha");
    expect(response?.status()).toBe(200);
    expect(response?.request().redirectedFrom()).toBeNull();
    expect(response?.headers()["x-frame-options"]).toBe("DENY");
    expect(response?.headers()["cache-control"]).toContain("no-store");
    expect(response?.headers()["referrer-policy"]).toBe("no-referrer");
    await expect.poll(() => page.evaluate(() =>
      (window as unknown as { nativeMessages: unknown[] }).nativeMessages,
    )).toEqual([outcome === "token" ? { type: "token", token: "synthetic-native-token" } : { type: "error" }]);
    expect(requests).toHaveLength(1);
    expect(requests[0]).toContain("https://challenges.cloudflare.com/turnstile/v0/api.js?");
    expect(await page.context().cookies()).toEqual([]);
    expect(await page.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }))).not.toContain("synthetic-native-token");
  });
}

test("a regular browser visit does not start a challenge", async ({ page }) => {
  const requests = await prepare(page, "token", false);
  await page.goto("/auth/native-captcha");
  await page.waitForLoadState("networkidle");
  expect(requests).toEqual([]);
});

test("closing a pending native document starts no authentication request", async ({ page }) => {
  const requests = await prepare(page, "pending");
  await page.goto("/auth/native-captcha");
  await expect.poll(() => page.evaluate(() => Boolean(
    (window as unknown as { syntheticCaptcha?: unknown }).syntheticCaptcha,
  ))).toBe(true);
  expect(await page.evaluate(() => (window as unknown as { nativeMessages: unknown[] }).nativeMessages)).toEqual([]);
  await page.goto("about:blank");
  expect(requests).toHaveLength(1);
});
