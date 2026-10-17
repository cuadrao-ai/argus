import { expect, test } from "@playwright/test";

for (const path of ["/", "/en"]) {
  test(`${path} preserves the capture story and accessible progress rail`, async ({
    page,
  }) => {
    await page.goto(path);
    const tabs = page.getByRole("tab");
    await expect(tabs).toHaveCount(3);
    await tabs.first().focus();
    await page.keyboard.press("ArrowRight");
    await expect(tabs.nth(1)).toBeFocused();
    await expect(tabs.nth(1)).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toContainText("RD$ 1,250");
    await page.keyboard.press("End");
    await expect(tabs.last()).toHaveAttribute("aria-selected", "true");
    await expect(page.getByRole("tabpanel")).toContainText(
      path === "/" ? "Aprobado" : "Approved",
    );
    await expect(page.locator("iframe")).toHaveCount(0);
  });
}

test("header blends at the top and becomes a pill after scrolling", async ({
  page,
}) => {
  await page.goto("/");
  const header = page.locator("header");
  expect(
    await header.evaluate((node) => getComputedStyle(node).borderRadius),
  ).toBe("0px");
  await page.evaluate(() => window.scrollTo(0, 350));
  await expect
    .poll(() => header.evaluate((node) => getComputedStyle(node).borderRadius))
    .toBe("44px");
  await expect(
    header.getByRole("img", { name: "cuadrao", exact: true }),
  ).toBeVisible();
});

for (const locale of ["es", "en"] as const) {
  test(`${locale} header separates language controls and links to how it works`, async ({ page }) => {
    const home = locale === "es" ? "/" : "/en";
    await page.goto(home);
    const header = page.locator("header");
    const menu = header.getByRole("button", { name: /Abrir menú|Open menu/ });
    const mobile = await menu.isVisible();
    if (mobile) {
      await menu.click();
      await page.keyboard.press("Escape");
      await expect(menu).toBeFocused();
      await menu.click();
    }
    const navigation = header.locator("nav:visible");
    const languages = navigation.getByRole("group", { name: locale === "es" ? "Idioma" : "Language" });
    await expect(languages.getByRole("link", { name: locale.toUpperCase(), exact: true })).toHaveAttribute("aria-current", "true");
    for (const language of ["es", "en"]) {
      const link = languages.getByRole("link", { name: language.toUpperCase(), exact: true });
      await expect(link).toHaveAttribute("href", language === "es" ? "/" : "/en");
      const bounds = await link.boundingBox();
      expect(bounds!.width).toBeGreaterThanOrEqual(44);
      expect(bounds!.height).toBeGreaterThanOrEqual(44);
    }
    await navigation.getByRole("link", { name: locale === "es" ? "Cómo funciona" : "How it works", exact: true }).click();
    await expect(page).toHaveURL(`${home}#el-producto`);
    if (mobile) await menu.click();
    await header.locator("nav:visible").getByRole("group").getByRole("link", { name: locale === "es" ? "EN" : "ES", exact: true }).click();
    await expect(page).toHaveURL(locale === "es" ? "/en" : "/");
  });
}

test("reduced motion is static and small screens do not overflow", async ({
  page,
}) => {
  await page.setViewportSize({ width: 320, height: 740 });
  await page.emulateMedia({ reducedMotion: "reduce" });
  for (const path of [
    "/",
    "/en",
    "/personal",
    "/en/personal",
    "/contacto",
    "/en/contact",
    "/privacidad",
    "/en/privacy",
  ]) {
    await page.goto(path);
    await expect(
      page.getByRole("button", { name: /Pausar animación|Pause animation/ }),
    ).toBeHidden();
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth - window.innerWidth,
    );
    expect(overflow, path).toBeLessThanOrEqual(1);
    const external = await page
      .locator('img[src^="http://127.0.0.1:4511"]')
      .count();
    expect(external).toBe(0);
  }
});

for (const path of ["/", "/en"]) {
  test(`${path} omits the editorial photo section and withdrawn product capture`, async ({ page }) => {
    await page.goto(path);
    await expect(
      page.locator('img[src*="business-review"], a[href*="business-review"], main img[src*="florist"], main img[src*="accountant"]'),
    ).toHaveCount(0);
    await expect(page.getByRole("region", { name: /EL TRABAJO DE CADA DÍA|EVERYDAY WORK/ })).toHaveCount(0);
    await expect(page.getByText(/Imágenes ilustrativas generadas con IA|AI-generated illustrative images/)).toHaveCount(0);
  });
}
