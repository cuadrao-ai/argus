import { expect, test } from "@playwright/test";

for (const path of ["/", "/en", "/personal", "/en/personal"]) {
  test(`${path} ends at the cropped wordmark without a photo reveal`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const footer = page.locator("footer");
    if (path.startsWith("/en")) await expect(footer.locator("[data-footer-credits]")).toHaveCount(0);
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
  test(`${path} reveals the local credit beside the copyright`, async ({ page }, info) => {
    await page.goto(path);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const footer = page.locator("footer");
    const credits = footer.locator("[data-footer-credits]");
    const copyright = credits.getByText("© Cuadrao LLC 2026", { exact: true });
    const local = credits.getByText("Hecho con ♥ para la República Dominicana", { exact: true });
    const reveal = credits.locator(":scope > div");
    await expect(copyright).toHaveCount(1);
    await expect(footer).not.toContainText("Mountain Road");
    await credits.scrollIntoViewIfNeeded();
    await page.mouse.move(0, 0);
    if (info.project.name === "mobile") {
      await expect(reveal).toBeHidden();
      await credits.tap();
      await expect(reveal).toBeHidden();
      await page.emulateMedia({ reducedMotion: "reduce" });
      await expect(reveal).toBeHidden();
      await footer.screenshot({ path: info.outputPath("footer-mobile.png") });
      return;
    }
    await expect.poll(() => reveal.evaluate((node) => node.getBoundingClientRect().width)).toBe(0);
    const before = (await copyright.boundingBox())!;
    const right = (await credits.boundingBox())!;
    await footer.screenshot({ path: info.outputPath("footer-rest.png") });
    await credits.hover();
    await expect.poll(() => local.evaluate((node) => getComputedStyle(node).clipPath)).toBe("inset(0px)");
    await expect.poll(async () => (await copyright.boundingBox())!.x).toBeLessThan(before.x - 100);
    expect(Math.abs((await credits.boundingBox())!.x + (await credits.boundingBox())!.width - right.x - right.width)).toBeLessThan(1);
    expect(await local.evaluate((node) => getComputedStyle(node).color)).toBe(await copyright.evaluate((node) => getComputedStyle(node).color));
    await expect(reveal).toHaveCSS("transition-duration", "0.7s");
    await expect(local).toHaveCSS("transition-duration", "0.5s");
    await expect(local).toHaveCSS("transition-delay", "0.1s");
    await footer.screenshot({ path: info.outputPath("footer-hover.png") });
    await page.mouse.move(0, 0);
    await expect(local).toHaveCSS("transition-delay", "0s");
    await expect.poll(() => reveal.evaluate((node) => node.getBoundingClientRect().width)).toBe(0);
    await footer.screenshot({ path: info.outputPath("footer-restored.png") });
    await page.emulateMedia({ reducedMotion: "reduce" });
    await expect.poll(() => reveal.evaluate((node) => node.getBoundingClientRect().width)).toBeGreaterThan(100);
    await expect(reveal).toHaveCSS("transition-duration", "0s");
    await expect(local).toHaveCSS("transition-duration", "0s");
    await footer.screenshot({ path: info.outputPath("footer-reduced-motion.png") });
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
