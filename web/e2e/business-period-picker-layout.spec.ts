import { expect, test, type Page } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

test.skip(process.env.NEXT_PUBLIC_BUSINESS_PILOT_ENABLED !== "true", "/dev/business-preview needs the Business pilot server");

async function openPicker(page: Page, width: number) {
  await page.setViewportSize({ width, height: 900 });
  await page.addInitScript(() => { const style = document.createElement("style"); style.textContent = "nextjs-portal { display: none !important; }"; document.addEventListener("DOMContentLoaded", () => document.head.appendChild(style)); });
  await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto("/dev/business-preview?chat=off");
  await page.getByRole("button", { name: /^Registros/ }).or(page.getByRole("link", { name: /^Registros/ })).first().click();
  await page.locator('[data-testid="records-toolbar"] button[aria-haspopup="dialog"]').nth(width > 900 ? 1 : 0).click();
  await expect(page.getByTestId("range-picker")).toBeVisible();
  return page.locator('[aria-label="Períodos rápidos"] button');
}

for (const width of [1366, 1440, 390]) test(`preset labels stay on one line and selecting one moves nothing at ${width}px`, async ({ page }) => {
  const rows = await openPicker(page, width);
  const names = await rows.allTextContents();
  const measure = () => rows.evaluateAll((nodes) => nodes.map((node) => {
    const origin = nodes[0].getBoundingClientRect();
    const box = node.getBoundingClientRect();
    const text = node.firstChild as ChildNode;
    const range = document.createRange(); range.selectNodeContents(text);
    return { x: Math.round(box.x - origin.x), y: Math.round(box.y - origin.y), width: Math.round(box.width), height: Math.round(box.height), lines: new Set([...range.getClientRects()].map((rect) => Math.round(rect.top))).size, overflow: node.scrollWidth > node.clientWidth };
  }));
  const before = await measure();
  expect(before.every((row) => row.lines === 1 && !row.overflow)).toBe(true);
  for (const name of names) {
    await rows.filter({ hasText: new RegExp(`^${name}$`) }).click();
    expect(await measure(), `selecting ${name}`).toEqual(before);
  }
});
