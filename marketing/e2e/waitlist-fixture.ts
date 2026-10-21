import type { Page } from "@playwright/test";

export async function mockWaitlistWidget(page: Page) {
  await page.route("**/api/signups/config", (route) => route.fulfill({ json: { siteKey: "fixture-site-key" } }));
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js*", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.turnstile={render:(_,o)=>{o.callback('fixture-token');return 'fixture';},remove:()=>{}};",
  }));
}
