import { expect, test } from "@playwright/test";

for (const { path, cta, contact, earlyAccess } of [
  { path: "/", cta: "Hablemos de tu negocio", contact: "Contacto", earlyAccess: "Acceso anticipado" },
  { path: "/en", cta: "Let’s talk about your business", contact: "Contact", earlyAccess: "Early access" },
]) {
  test(`${path} Business contact actions lead to /contacto`, async ({ page }) => {
    await page.goto(path);
    const actions = page.getByRole("link", { name: cta, exact: true, includeHidden: true });
    await expect(actions).toHaveCount(3);
    for (const action of await actions.all()) {
      await expect(action).toHaveAttribute("href", "/contacto");
    }
    await expect(page.locator("footer").getByRole("link", { name: contact, exact: true })).toHaveAttribute("href", "/contacto");

    const menu = page.getByRole("button", { name: /Abrir menú|Open menu/ });
    if (await menu.isVisible()) {
      await menu.click();
      await expect(page.locator("#business-mobile-menu").getByRole("link", { name: cta, exact: true })).toHaveAttribute("href", "/contacto");
      await page.getByRole("button", { name: /Cerrar menú|Close menu/ }).click();
    }
    await page.locator("main").getByRole("link", { name: cta, exact: true }).click();
    await expect(page).toHaveURL(/\/contacto$/);
    await expect(page.getByRole("heading", { level: 1 })).toHaveText(/Empecemos por\s+tu negocio\./);
  });

  test(`${path} Personal waitlist actions keep their destinations`, async ({ page }) => {
    const personal = path === "/" ? "/personal" : "/en/personal";
    await page.goto(personal);
    await expect(page.locator("header").getByRole("link", { name: earlyAccess, exact: true, includeHidden: true })).toHaveAttribute("href", "#early-access");
    await expect(page.locator("footer").getByRole("link", { name: earlyAccess, exact: true })).toHaveAttribute("href", `${personal}#early-access`);
    const menu = page.getByRole("button", { name: /Abrir menú|Open menu/ });
    if (await menu.isVisible()) {
      await menu.click();
      await expect(page.locator("#business-mobile-menu").getByRole("link", { name: earlyAccess, exact: true })).toHaveAttribute("href", "#early-access");
    }
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
    const header = page.locator("header nav > div:last-child > a:last-child");
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

test("/personal header button rests on the green once the header floats", async ({ page }) => {
  test.skip(test.info().project.name === "mobile", "the header button is in the mobile menu on phones");
  await page.goto("/personal");
  const button = page.locator("header nav > div:last-child > a:last-child");
  await page.evaluate(() => window.scrollTo(0, 800));
  await expect(page.locator("header")).toHaveAttribute("data-condensed", "true");
  await page.mouse.move(2, 2);
  await expect.poll(() => button.evaluate((el) => getComputedStyle(el).backgroundColor)).toBe(GREEN);
});
