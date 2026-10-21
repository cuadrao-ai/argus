// The web with NEXT_PUBLIC_BUSINESS_PILOT_ENABLED unset and the API in S1: /biz and the home shell, as owner A and signed out.
import { createRequire } from "module";
import { readFileSync, writeFileSync } from "fs";
import { join } from "path";

const WORKTREE = "/Users/garces/Documents/projects/repos/argus-worktrees/business-pilot-spaces";
const { chromium } = createRequire(join(WORKTREE, "web", "package.json"))("playwright");
const HERE = new URL(".", import.meta.url).pathname;
const APP = "http://localhost:3641";
const A = JSON.parse(readFileSync(join(HERE, "world.json"), "utf8")).A;
const browser = await chromium.launch();
const page = await (await browser.newContext({ viewport: { width: 1280, height: 800 }, locale: "en-US" })).newPage();
const apiCalls = [];
page.on("request", (r) => { if (r.url().includes(":8641/")) apiCalls.push(`${r.method()} ${new URL(r.url()).pathname}`); });
await page.goto(`${APP}/?auth=login`);
await page.waitForLoadState("networkidle");
await page.locator('input[type="email"]').fill(A.email);
await page.locator('input[type="password"]').fill(A.password);
await page.locator('button[type="submit"]').last().click();
await page.waitForURL((url) => !url.search.includes("auth=login"), { timeout: 30_000 });
await page.waitForTimeout(3000);
const homeNav = await page.getByTestId("business-sidebar-nav").isVisible().catch(() => false);
const homeText = (await page.locator("body").innerText()).replace(/\s+/g, " ");
await page.screenshot({ path: join(HERE, "results", "web-flag-off-home.png") });
const biz = await page.goto(`${APP}/biz`);
await page.waitForTimeout(4000);
await page.screenshot({ path: join(HERE, "results", "web-flag-off-biz.png") });
const bizNav = await page.getByTestId("business-sidebar-nav").isVisible().catch(() => false);
const bizText = (await page.locator("body").innerText()).replace(/\s+/g, " ").slice(0, 200);
await browser.close();
const anon = await fetch(`${APP}/biz`, { redirect: "manual" });
const anonBody = await anon.text();
const missing = await fetch(`${APP}/no-such-page`, { redirect: "manual" }).then((r) => r.status);
const out = {
  signed_in_home_business_nav_visible: homeNav,
  signed_in_home_mentions_business_merchants: ["FERRETERIA", "COLMADO", "FARMACIA", "Operativa A"].filter((n) => homeText.includes(n)),
  signed_in_biz_http: biz?.status(), signed_in_biz_business_nav_visible: bizNav, signed_in_biz_text: bizText,
  signed_out_biz_http: anon.status, signed_out_biz_is_not_found_page: anonBody.includes("This page could not be found"),
  no_such_page_http: missing,
  business_api_calls_from_web: [...new Set(apiCalls.filter((c) => c.includes("/business") || c.includes("/whatsapp")))],
};
writeFileSync(join(HERE, "results", "web-flag-off.json"), JSON.stringify(out, null, 1));
console.log(JSON.stringify(out));
