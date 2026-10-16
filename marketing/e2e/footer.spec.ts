import { expect, test } from "@playwright/test";

for (const path of ["/", "/en", "/personal", "/en/personal"]) {
  test(`${path} ends at the cropped wordmark without a photo reveal`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const footer = page.locator("footer");
    const brand = footer.getByRole("img", { name: "cuadrao", exact: true });
    await expect(footer.locator("img")).toHaveCount(1);
    await expect(brand).toHaveAttribute("src", `/cuadrao-site/cuadrao-lockup-${path.includes("personal") ? "light" : "dark"}.svg`);
    await brand.scrollIntoViewIfNeeded();
    await expect.poll(() => brand.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    await expect(page.locator("[data-footer-peek]")).toHaveCount(0);
    const crop = footer.locator(':scope > div[aria-hidden="true"]');
    await expect(crop).toHaveText("cuadrao");
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect.poll(() => crop.evaluate((node) =>
      Math.abs(node.getBoundingClientRect().bottom - innerHeight),
    )).toBeLessThanOrEqual(1);
    expect(await crop.evaluate((node) =>
      getComputedStyle(node).overflow === "hidden" &&
      node.firstElementChild!.getBoundingClientRect().bottom > node.getBoundingClientRect().bottom,
    )).toBe(true);
    const ending = await page.evaluate(() => ({ height: document.documentElement.scrollHeight, scroll: scrollY }));
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(600);
    const after = await page.evaluate(() => ({ height: document.documentElement.scrollHeight, scroll: scrollY }));
    expect(after.height).toBe(ending.height);
    expect(Math.abs(after.scroll - ending.scroll)).toBeLessThanOrEqual(1);
    await expect(footer.locator("img")).toHaveCount(1);
  });
}

for (const path of ["/", "/personal"]) {
  test(`${path} shows the approved company and local credit`, async ({ page }) => {
    await page.goto(path);
    const footer = page.locator("footer");
    await expect(footer.getByText("© Cuadrao LLC 2026", { exact: true })).toHaveCount(1);
    await expect(footer.getByText("Hecho con ♥ para la República Dominicana", { exact: true })).toBeVisible();
    await expect(footer).not.toContainText("Mountain Road");
  });
}

test("the Business footer opens the same product section as the hero", async ({ page }) => {
  await page.goto("/");
  const link = page.locator("footer").getByRole("link", { name: "Ver cómo funciona", exact: true });
  await expect(link).toHaveAttribute("href", "/#el-producto");
  await link.click();
  await expect(page).toHaveURL(/\/#el-producto$/);
  await expect(page.locator("#el-producto")).toBeInViewport();
});
