import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

for (const width of [390, 1440]) test(`Bandeja tabs stay inside the page at ${width}px`, async ({ page }) => {
  await page.setViewportSize({ width, height: 844 });
  await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  await page.goto("/dev/business-preview?view=inbox");
  const reception = page.getByTestId("reception-preview");
  await expect(reception).toBeVisible();
  await expect(reception.getByTestId("reception-count-attention")).not.toHaveText("-");
  await expect(reception.locator("#reception-list > ul > li").first()).toBeVisible();
  await page.evaluate(() => document.fonts.ready);
  const tabs = width === 390 ? ["all", "attention", "listos", "eliminados"] : ["eliminados"];
  for (const tab of tabs) {
    await page.locator(`#reception-tab-${tab}`).click();
    await expect(page.locator(`#reception-tab-${tab}`)).toHaveAttribute("aria-selected", "true");
    await expect(reception.getByTestId("reception-pending")).toHaveCount(0);
    if (tab === "eliminados") await expect(reception.getByTestId("reception-empty")).toBeVisible();
    const layout = await reception.evaluate(section => {
      const describe = (element: Element) => `${element.tagName.toLowerCase()}${element.id ? `#${element.id}` : ""}.${element.className}`;
      const ancestors = [];
      // The tab strip may scroll internally; its parents and the page may not.
      for (let element = section.querySelector('[role="tablist"]')?.parentElement; element; element = element.parentElement) {
        ancestors.push({ element: describe(element), scrollLeft: element.scrollLeft });
      }
      return {
        documentScrollLeft: document.scrollingElement?.scrollLeft,
        scrolledAncestors: ancestors.filter(element => element.scrollLeft !== 0),
        wideElements: [...document.querySelectorAll("body *")].filter(element => element.getBoundingClientRect().width > window.innerWidth).map(element => ({ element: describe(element), width: element.getBoundingClientRect().width })),
      };
    });
    if (process.env.RECEPTION_CAPTURE) {
      await mkdir("../temp/2335", { recursive: true });
      await page.screenshot({ path: `../temp/2335/${process.env.RECEPTION_CAPTURE}-${width}-${tab}.png`, animations: "disabled" });
      console.log(tab, JSON.stringify(layout));
    }
    expect.soft(layout.documentScrollLeft, tab).toBe(0);
    expect.soft(layout.scrolledAncestors, tab).toEqual([]);
    expect.soft(layout.wideElements, tab).toEqual([]);
  }
});
