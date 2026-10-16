import { expect, test } from "@playwright/test";

for (const path of ["/", "/personal", "/en", "/en/personal"]) {
  test(`${path} keeps the reference crop at the document end`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const crop = page.locator('footer > div[aria-hidden="true"]');
    await crop.scrollIntoViewIfNeeded();
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    const width = page.viewportSize()!.width;
    const mobile = width <= 800;
    const personal = path.includes("personal");
    await expect(crop).toHaveCSS("padding-top", mobile ? "10px" : personal ? "0px" : "18px");
    await expect(crop).toHaveCSS("border-top-width", mobile || !personal ? "1px" : "0px");
    const height = width * (mobile ? 0.22 : personal ? 0.20 : 0.21);
    expect(Math.abs((await crop.boundingBox())!.height - height)).toBeLessThan(0.1);
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
