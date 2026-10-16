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
