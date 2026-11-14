import { expect, test } from "@playwright/test";

import { SITE_ROUTES } from "../lib/site-routes";

for (const path of ["/", "/en"]) {
  test(`${path} ends at the wordmark without a photo reveal`, async ({ page }) => {
    await page.goto(path);
    await page.evaluate(() => document.fonts.ready);
    const footer = page.locator("footer");
    await expect(footer.locator("[data-footer-credits]")).toHaveCount(1);
    const brand = footer.getByRole("img", { name: "cuadrao", exact: true });
    await expect(footer.locator("img")).toHaveCount(1);
    await expect(brand).toHaveAttribute("src", "/cuadrao-site/cuadrao-lockup-dark.svg");
    await brand.scrollIntoViewIfNeeded();
    await expect.poll(() => brand.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    await expect(page.locator("[data-footer-peek]")).toHaveCount(0);
    const crop = footer.locator(':scope > div[aria-hidden="true"]');
    await expect(crop).toHaveText("cuadrao");
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    await expect.poll(() => crop.evaluate((node) =>
      Math.abs(node.getBoundingClientRect().bottom - innerHeight),
    )).toBeLessThanOrEqual(1);
    const ending = await page.evaluate(() => ({ height: document.documentElement.scrollHeight, scroll: scrollY }));
    await page.mouse.wheel(0, 600);
    await page.waitForTimeout(600);
    const after = await page.evaluate(() => ({ height: document.documentElement.scrollHeight, scroll: scrollY }));
    expect(after.height).toBe(ending.height);
    expect(Math.abs(after.scroll - ending.scroll)).toBeLessThanOrEqual(1);
    await expect(footer.locator("img")).toHaveCount(1);
  });
}

for (const path of ["/", "/contacto", "/privacidad", "/terminos", "/eliminar-datos", "/en", "/en/contact", "/en/privacy", "/en/terms", "/en/delete-data"]) {
  test(`${path} reveals the local credit beside the copyright`, async ({ page }, info) => {
    await page.goto(path);
    await page.emulateMedia({ reducedMotion: "no-preference" });
    const footer = page.locator("footer");
    const credits = footer.locator("[data-footer-credits]");
    const copyright = credits.getByText("© Cuadrao LLC 2026", { exact: true });
    const local = credits.getByText(path.startsWith("/en") ? "Made with ♥ for the Dominican Republic" : "Hecho con ♥ para la República Dominicana", { exact: true });
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
    const rest = (await credits.boundingBox())!;
    await footer.screenshot({ path: info.outputPath("footer-rest.png") });
    await credits.hover();
    await expect.poll(() => local.evaluate((node) => getComputedStyle(node).clipPath)).toBe("inset(0px)");
    await expect.poll(async () => (await credits.boundingBox())!.width).toBeGreaterThan(rest.width + 100);
    expect(Math.abs((await copyright.boundingBox())!.x - before.x)).toBeLessThan(1);
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

for (const path of ["/", "/en"]) {
  test(`${path} footer links are at least 14px`, async ({ page }) => {
    await page.goto(path);
    const small = await page.locator('footer nav a, footer a[href="#top"]').evaluateAll((nodes) =>
      nodes.flatMap((node) => {
        const size = getComputedStyle(node).fontSize;
        return Number.parseFloat(size) >= 14 ? [] : [`${node.textContent} ${size}`];
      }),
    );
    expect(small).toEqual([]);
  });

  test(`${path} footer links stay on one line on a 375px phone`, async ({ page }) => {
    test.skip(test.info().project.name !== "mobile", "phone layout");
    await page.setViewportSize({ width: 375, height: 812 });
    await page.goto(path);
    const wrapped = await page.locator("footer nav a").evaluateAll((nodes) =>
      nodes.flatMap((node) => (node.getBoundingClientRect().height > 44 ? [node.textContent] : [])),
    );
    expect(wrapped).toEqual([]);
  });
}

for (const path of ["/", "/en"]) {
  test(`${path} footer keeps social icons under the brand and back to top beside the copyright`, async ({ page }) => {
    await page.goto(path);
    const footer = page.locator("footer");
    const tagline = footer.locator('[class*="footerIdentity"] > p');
    const social = footer.locator('[class*="footerIdentity"]').getByRole("group", { name: path === "/" ? "Redes sociales" : "Social media" });
    await social.scrollIntoViewIfNeeded();
    await expect(social.getByRole("link", { name: "Instagram" })).toHaveAttribute("href", "https://www.instagram.com/cuadraoai/");
    const grid = (await footer.locator('[class*="businessFooterGrid"]').boundingBox())!;
    const brand = (await tagline.boundingBox())!;
    const icons = (await social.boundingBox())!;
    expect(icons.y).toBeGreaterThanOrEqual(brand.y + brand.height);
    expect(Math.abs(icons.x - brand.x)).toBeLessThan(1);
    const copyright = (await footer.getByText("© Cuadrao LLC 2026", { exact: true }).boundingBox())!;
    const top = (await footer.locator('a[href="#top"]').boundingBox())!;
    expect(Math.abs(copyright.x - grid.x)).toBeLessThan(1);
    expect(Math.abs(top.x + top.width - (grid.x + grid.width))).toBeLessThan(1);
    expect(Math.abs(copyright.y + copyright.height / 2 - (top.y + top.height / 2))).toBeLessThan(2);
  });
}

test("the Business footer opens the same product section as the hero", async ({ page }) => {
  await page.goto("/");
  const link = page.locator("footer").getByRole("link", { name: "Ver cómo funciona", exact: true });
  await expect(link).toHaveAttribute("href", "/#como");
  await link.click();
  await expect(page).toHaveURL(/\/#como$/);
  await expect(page.locator("#como")).toBeInViewport();
});

for (const { path } of SITE_ROUTES) {
  test(`${path} menu button and footer links are at least 44px on a phone`, async ({ page }) => {
    test.skip(test.info().project.name !== "mobile", "phone tap targets");
    await page.setViewportSize({ width: 320, height: 800 });
    await page.goto(path);
    const targets = page.locator('header button[aria-controls="business-mobile-menu"], footer nav a');
    const short = await targets.evaluateAll((nodes) =>
      nodes.flatMap((node) => {
        const { width, height } = node.getBoundingClientRect();
        return width >= 44 && height >= 44 ? [] : [`${node.textContent} ${width}x${height}`];
      }),
    );
    expect(short).toEqual([]);
  });
}
