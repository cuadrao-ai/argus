import { expect, test } from "@playwright/test";

for (const path of ["/", "/personal", "/en", "/en/personal"]) {
  test(`${path} shows a full mobile wordmark and keeps the desktop crop without a divider`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const crop = page.locator('footer > div[aria-hidden="true"]');
    await crop.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const width = page.viewportSize()!.width;
    const mobile = width <= 800;
    const borderVisible = await crop.evaluate((node) => {
      const style = getComputedStyle(node);
      return style.borderTopStyle !== "none" && style.borderTopWidth !== "0px" &&
        style.borderTopColor !== "rgba(0, 0, 0, 0)";
    });
    expect(borderVisible).toBe(false);
    const ending = await crop.evaluate((node) => ({
      documentHeight: document.documentElement.scrollHeight,
      scroll: scrollY,
      bottom: node.getBoundingClientRect().bottom,
      wordBottom: node.firstElementChild!.getBoundingClientRect().bottom,
      viewportHeight: innerHeight,
      bottomPadding: Number.parseFloat(getComputedStyle(node).paddingBottom),
    }));
    expect(Math.abs(ending.bottom - ending.viewportHeight)).toBeLessThan(1);
    if (mobile) {
      expect(ending.wordBottom).toBeLessThanOrEqual(ending.bottom - ending.bottomPadding + 1);
    } else {
      expect(ending.wordBottom).toBeGreaterThan(ending.bottom);
    }
    await page.mouse.wheel(0, 800);
    await expect.poll(() => page.evaluate(() => document.documentElement.scrollHeight)).toBe(ending.documentHeight);
    await expect.poll(() => page.evaluate(() => scrollY)).toBe(ending.scroll);
  });
}
