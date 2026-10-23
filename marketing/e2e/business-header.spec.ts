import { expect, test } from "@playwright/test";

const cases = [
  { home: "/", other: "/en", language: "Idioma", cta: "Hablemos de tu negocio", login: "Iniciar sesión" },
  { home: "/en", other: "/", language: "Language", cta: "Let’s talk about your business", login: "Log in" },
] as const;

for (const { home, other, language, cta, login } of cases) {
  test(`${home} Business header keeps language, contact, and login in order`, async ({ page }) => {
    await page.goto(home);
    const header = page.locator("header");
    const menu = header.getByRole("button", { name: /Abrir menú|Open menu/ });
    if (await menu.isVisible()) await menu.click();
    const nav = header.locator("nav:visible");
    const group = nav.getByRole("group", { name: language });
    const contact = nav.getByRole("link", { name: cta, exact: true });
    const loginButton = nav.getByRole("button", { name: login, exact: true });
    await expect(group).toBeVisible();
    expect((await group.boundingBox())!.width).toBeLessThan(120);
    await expect(contact).toHaveAttribute("href", "/contacto");
    await expect(loginButton).toBeEnabled();
    await expect(loginButton).toHaveAttribute("data-preview-unwired", "true");
    await expect(nav.getByRole("link", { name: /Cómo funciona|How it works|Nosotros|About/, exact: true })).toHaveCount(0);
    const boxes = await Promise.all([group, contact, loginButton].map((node) => node.boundingBox()));
    if (test.info().project.name === "mobile") {
      expect(boxes[0]!.y).toBeLessThan(boxes[1]!.y);
      expect(boxes[1]!.y).toBeLessThan(boxes[2]!.y);
      expect(await page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth)).toBeLessThanOrEqual(1);
    } else {
      expect(boxes[0]!.x).toBeLessThan(boxes[1]!.x);
      expect(boxes[1]!.x).toBeLessThan(boxes[2]!.x);
      await page.evaluate(() => window.scrollTo(0, 350));
      await expect(header).toHaveAttribute("data-condensed", "true");
    }
    const target = group.getByRole("link", { name: other === "/en" ? "EN" : "ES", exact: true });
    await expect(target).toHaveAttribute("href", other);
    await target.click();
    await expect(page).toHaveURL(other);
  });
}

test("Business contact and login show pointer and keyboard states without changing scroll treatment", async ({ page }) => {
  test.skip(test.info().project.name === "mobile", "desktop header states");
  await page.goto("/");
  const header = page.locator("header");
  const contact = header.getByRole("link", { name: "Hablemos de tu negocio" });
  const login = header.getByRole("button", { name: "Iniciar sesión" });
  await expect(header).toHaveAttribute("data-condensed", "false");
  await expect(contact).toHaveCSS("background-color", "rgb(232, 237, 227)");
  await contact.hover();
  await expect(contact).toHaveCSS("background-color", "rgb(47, 90, 73)");
  await expect(contact).toHaveCSS("color", "rgb(255, 255, 255)");
  await page.mouse.move(0, 200);
  await contact.focus();
  await page.keyboard.press("Shift+Tab");
  await page.keyboard.press("Tab");
  await expect(contact).toBeFocused();
  await expect(contact).toHaveCSS("background-color", "rgb(47, 90, 73)");
  await expect(contact).toHaveCSS("outline-style", "solid");

  await expect(login).toBeEnabled();
  await expect(login).toHaveAttribute("data-preview-unwired", "true");
  await expect(login).toHaveCSS("color", "rgb(47, 90, 73)");
  await expect(login).toHaveCSS("border-top-left-radius", "999px");
  await login.hover();
  await expect(login).toHaveCSS("color", "rgb(47, 90, 73)");
  await expect(login).toHaveCSS("text-decoration-line", "underline");
  await expect(login).toHaveCSS("cursor", "pointer");
  await page.mouse.move(0, 200);
  await contact.focus();
  await page.keyboard.press("Tab");
  await expect(login).toBeFocused();
  await expect(login).toHaveCSS("text-decoration-line", "underline");
  await expect(login).toHaveCSS("outline-style", "solid");
  const before = page.url();
  await login.click();
  await expect(page).toHaveURL(before);

  await page.evaluate(() => window.scrollTo(0, 350));
  await expect(header).toHaveAttribute("data-condensed", "true");
  await contact.blur();
  await login.blur();
  await expect(contact).toHaveCSS("background-color", "rgb(47, 90, 73)");
  await contact.hover();
  await expect(contact).toHaveCSS("background-color", "rgb(29, 66, 54)");
});

test("Business language track gaps belong to the links", async ({ page }) => {
  test.skip(test.info().project.name === "mobile", "desktop pointer check");
  await page.goto("/");
  const group = page.locator("header").getByRole("group", { name: "Idioma" });
  const box = (await group.boundingBox())!;
  const points = [
    [box.x + 1, box.y + box.height / 2],
    [box.x + 3 + 48 + 1, box.y + box.height / 2],
    [box.x + box.width - 1, box.y + box.height / 2],
    [box.x + 27, box.y + 1],
    [box.x + 77, box.y + box.height - 1],
  ];
  for (const [x, y] of points) {
    const hit = await page.evaluate(([px, py]) => {
      const node = document.elementFromPoint(px, py);
      const link = node?.closest("a");
      return { href: link?.getAttribute("href"), cursor: node ? getComputedStyle(node).cursor : "none" };
    }, [x, y]);
    expect(hit.href).toMatch(/^\/(en)?$/);
    expect(hit.cursor).toBe("pointer");
  }
});

test("Business language thumb reaches on press and restores on cancel", async ({ page }) => {
  test.skip(test.info().project.name === "mobile", "desktop pointer check");
  await page.goto("/");
  const group = page.locator("header").getByRole("group", { name: "Idioma" });
  const target = group.getByRole("link", { name: "EN", exact: true });
  const thumb = group.locator('[aria-hidden="true"]');
  const before = (await thumb.boundingBox())!;
  await target.dispatchEvent("pointerdown", { button: 0, pointerType: "mouse" });
  await expect.poll(async () => (await thumb.boundingBox())!.width).toBeGreaterThan(before.width + 10);
  await target.dispatchEvent("pointercancel", { button: 0, pointerType: "mouse" });
  await expect.poll(async () => (await thumb.boundingBox())!.width).toBeCloseTo(before.width, 0);
  await expect(page).toHaveURL("/");
});

test("Business language links keep native modifier, keyboard, and no-script navigation", async ({ page, browser }) => {
  await page.goto("/");
  const menu = page.locator("header").getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  const target = page.locator("header nav:visible").getByRole("group", { name: "Idioma" }).getByRole("link", { name: "EN" });
  if (test.info().project.name === "desktop") {
    const opened = page.context().waitForEvent("page");
    await target.click({ modifiers: [process.platform === "darwin" ? "Meta" : "Control"] });
    const translated = await opened;
    await expect(translated).toHaveURL("/en");
    await translated.close();
    await expect(page).toHaveURL("/");
  }
  await target.focus();
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL("/en");

  const noScript = await browser.newContext({
    baseURL: new URL(page.url()).origin,
    javaScriptEnabled: false,
    viewport: { width: 1440, height: 900 },
  });
  try {
    const noScriptPage = await noScript.newPage();
    await noScriptPage.goto("/");
    const link = noScriptPage.locator("header nav:visible").getByRole("group", { name: "Idioma" }).getByRole("link", { name: "EN" });
    await expect(link).toHaveAttribute("href", "/en");
    await link.click();
    await expect(noScriptPage).toHaveURL("/en");
  } finally {
    await noScript.close();
  }
});

test("reduced motion uses direct language navigation", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/");
  const menu = page.locator("header").getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  await page.locator("header nav:visible").getByRole("group", { name: "Idioma" }).getByRole("link", { name: "EN" }).click();
  await expect(page).toHaveURL("/en");
});

test("Personal keeps its original language group and early access action", async ({ page }) => {
  await page.goto("/personal");
  const menu = page.locator("header").getByRole("button", { name: "Abrir menú" });
  if (await menu.isVisible()) await menu.click();
  const nav = page.locator("header nav:visible");
  await expect(nav.getByRole("group", { name: "Idioma" })).toHaveClass(/languages/);
  await expect(nav.getByRole("link", { name: "Acceso anticipado" })).toHaveAttribute("href", "#early-access");
  await expect(nav.getByRole("button", { name: "Iniciar sesión" })).toHaveCount(0);
  if (test.info().project.name === "desktop") {
    const access = nav.getByRole("link", { name: "Acceso anticipado" });
    await expect(access).toHaveCSS("background-color", "rgb(232, 237, 227)");
    await access.hover();
    await expect(access).toHaveCSS("background-color", "rgb(232, 237, 227)");
  }
});
