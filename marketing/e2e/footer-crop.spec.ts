import { expect, test } from "@playwright/test";

for (const path of ["/", "/personal", "/en", "/en/personal"]) {
  test(`${path} ends with the cropped wordmark and no extra mobile divider`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const crop = page.locator('footer > div[aria-hidden="true"]');
    await crop.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const width = page.viewportSize()!.width;
    const mobile = width <= 800;
    const personal = path.includes("personal");
    await expect(crop).toHaveCSS("border-top-width", mobile || personal ? "0px" : "1px");
    await expect(crop).toHaveCSS("overflow", "hidden");
    const ending = await crop.evaluate((node) => ({
      documentHeight: document.documentElement.scrollHeight,
      scroll: scrollY,
      bottom: node.getBoundingClientRect().bottom,
      wordBottom: node.firstElementChild!.getBoundingClientRect().bottom,
      viewportHeight: innerHeight,
    }));
    expect(Math.abs(ending.bottom - ending.viewportHeight)).toBeLessThan(1);
    expect(ending.wordBottom).toBeGreaterThan(ending.bottom);
    await page.mouse.wheel(0, 800);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBe(ending.documentHeight);
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(ending.scroll);
  });
}
