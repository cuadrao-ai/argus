import { expect, test } from "@playwright/test";

import { businessPath, SITE_ROUTES } from "../lib/site-routes";

for (const { path, cta, contact, contactPath, contactHeading } of [
  { path: "/", cta: "Hablemos de tu negocio", contact: "Contacto", contactPath: "/contacto", contactHeading: /Empecemos por\s+tu negocio\./ },
  { path: "/en", cta: "Let’s talk about your business", contact: "Contact", contactPath: "/en/contact", contactHeading: /Let’s start with\s+your business\./ },
]) {
  test(`${path} Business contact actions lead to ${contactPath}`, async ({ page }) => {
    await page.goto(path);
    const actions = page.getByRole("link", { name: cta, exact: true, includeHidden: true });
    await expect(actions).toHaveCount(3);
    for (const action of await actions.all()) {
      await expect(action).toHaveAttribute("href", contactPath);
    }
    await expect(page.locator("footer").getByRole("link", { name: contact, exact: true })).toHaveAttribute("href", contactPath);

    const menu = page.getByRole("button", { name: /Abrir menú|Open menu/ });
    if (await menu.isVisible()) {
      await menu.click();
      await expect(page.locator("#business-mobile-menu").getByRole("link", { name: cta, exact: true })).toHaveAttribute("href", contactPath);
      await page.getByRole("button", { name: /Cerrar menú|Close menu/ }).click();
    }
    await page.locator("main").getByRole("link", { name: cta, exact: true }).click();
    await expect(page).toHaveURL(new RegExp(`${contactPath}$`));
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(contactHeading);
  });
}

for (const { locale, path } of SITE_ROUTES) {
  test(`${path} never links to the contact page of the other language`, async ({ page }) => {
    const otherContact = businessPath(locale === "es" ? "en" : "es", "contact");
    await page.goto(path);
    await expect(page.locator(`a[href="${otherContact}"]:not([data-language-switch])`)).toHaveCount(0);
  });
}

const GREEN = "rgb(47, 90, 73)";
const DEEP = "rgb(29, 66, 54)";

for (const { path, cta } of [
  { path: "/", cta: "Hablemos de tu negocio" },
  { path: "/en", cta: "Let’s talk about your business" },
]) {
  test(`${path} dark buttons rest on the green and darken on hover`, async ({ page }) => {
    test.skip(test.info().project.name === "mobile", "the header button is in the mobile menu on phones");
    await page.goto(path);
    const background = (node: ReturnType<typeof page.locator>) => node.evaluate((el) => getComputedStyle(el).backgroundColor);
    const header = page.locator("header").getByRole("link", { name: cta, exact: true });
    const hero = page.locator("main").getByRole("link", { name: cta, exact: true }).first();
    const closing = page.locator("footer").getByRole("link", { name: cta, exact: true });

    await expect.poll(() => background(header)).toBe("rgb(232, 237, 227)");
    for (const button of [hero, closing]) {
      await button.scrollIntoViewIfNeeded();
      await page.mouse.move(2, 2);
      await expect.poll(() => background(button)).toBe(GREEN);
      await button.hover();
      await expect.poll(() => background(button)).toBe(DEEP);
    }

    await page.evaluate(() => window.scrollTo(0, 800));
    await expect(page.locator("header")).toHaveAttribute("data-condensed", "true");
    await page.mouse.move(2, 2);
    await expect.poll(() => background(header)).toBe(GREEN);
    await header.hover();
    await expect.poll(() => background(header)).toBe(DEEP);
  });
}
