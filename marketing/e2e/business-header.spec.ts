import { execFileSync } from "node:child_process";
import { chromium, expect, test, type Page } from "@playwright/test";

import { SITE_PORT } from "./ports";

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

const stagingHost = "cuadrao-marketing-staging.onrender.com";
const stagingSignIn = "https://cuadrao-web-staging.onrender.com/?auth=login";

for (const { home, login } of cases) {
  for (const method of ["mouse", "keyboard"] as const) {
    test(`${home} staging sign-in navigates with ${method}`, async () => {
      const mobile = test.info().project.name === "mobile";
      const browser = await chromium.launch({
        args: [`--host-resolver-rules=MAP ${stagingHost} 127.0.0.1`, "--no-proxy-server"],
      });
      const context = await browser.newContext({
        viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
        isMobile: mobile,
        hasTouch: mobile,
        serviceWorkers: "block",
      });
      const errors: string[] = [];
      try {
        await context.route("**/*", async (route) => {
          const url = new URL(route.request().url());
          if (url.hostname === stagingHost && url.port === String(SITE_PORT)) return route.continue();
          if (url.href === stagingSignIn && route.request().isNavigationRequest()) {
            return route.fulfill({ contentType: "text/html", body: "<!doctype html><title>Synthetic sign-in destination</title>" });
          }
          throw new Error(`Unexpected request to ${url.origin}`);
        });
        const page = await context.newPage();
        page.on("pageerror", (error) => errors.push(error.message));
        page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
        await page.goto(`http://${stagingHost}:${SITE_PORT}${home}`);
        const menu = page.locator("header").getByRole("button", { name: /Abrir menú|Open menu/ });
        if (mobile) await menu.click();
        const nav = page.locator("header nav:visible");
        const signIn = nav.getByRole("link", { name: login, exact: true });
        await expect(signIn).toHaveAttribute("href", stagingSignIn);
        await expect(nav.getByRole("button", { name: login, exact: true })).toHaveCount(0);
        await expect(signIn).toHaveCSS("color", "rgb(47, 90, 73)");
        const geometry = await signIn.evaluate((link) => {
          const measure = (node: Element) => {
            const css = getComputedStyle(node);
            const box = node.getBoundingClientRect();
            return { width: box.width, height: box.height, font: css.font, padding: css.padding, color: css.color, radius: css.borderRadius };
          };
          const button = document.createElement("button");
          button.className = link.className;
          button.textContent = link.textContent;
          link.replaceWith(button);
          const approvedButton = measure(button);
          button.replaceWith(link);
          return { approvedButton, signInLink: measure(link) };
        });
        expect(geometry.signInLink).toEqual(geometry.approvedButton);
        if (method === "mouse") {
          await test.info().attach("staging-signin.png", { body: await page.screenshot(), contentType: "image/png" });
          await test.info().attach("source-identity.json", {
            body: Buffer.from(JSON.stringify({
              commit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
              tree: execFileSync("git", ["rev-parse", "HEAD^{tree}"], { encoding: "utf8" }).trim(),
              viewport: page.viewportSize(),
              home,
              geometry,
              destination: stagingSignIn,
              destinationMode: "synthetic document, no hosted request",
            }, null, 2)),
            contentType: "application/json",
          });
        }
        await signIn.hover();
        await expect(signIn).toHaveCSS("text-decoration-line", "underline");
        if (method === "keyboard") {
          await signIn.focus();
          await page.keyboard.press("Shift+Tab");
          await page.keyboard.press("Tab");
          await expect(signIn).toBeFocused();
          await expect(signIn).toHaveCSS("outline-style", "solid");
          await page.keyboard.press("Enter");
        } else {
          await signIn.click();
        }
        await expect(page).toHaveURL(stagingSignIn);
        expect(errors).toEqual([]);
      } finally {
        await context.close();
        await browser.close();
      }
    });
  }
}

test("public Marketing never exposes the staging sign-in link", async () => {
  const browser = await chromium.launch({
    args: ["--host-resolver-rules=MAP cuadrao.ai 127.0.0.1", "--no-proxy-server"],
  });
  try {
    const mobile = test.info().project.name === "mobile";
    const page = await browser.newPage({
      viewport: mobile ? { width: 390, height: 844 } : { width: 1440, height: 900 },
    });
    await page.goto(`http://cuadrao.ai:${SITE_PORT}/`);
    if (mobile) await page.getByRole("button", { name: "Abrir menú" }).click();
    const nav = page.locator("header nav:visible");
    await expect(nav.getByRole("link", { name: "Iniciar sesión", exact: true })).toHaveCount(0);
    const signIn = nav.getByRole("button", { name: "Iniciar sesión", exact: true });
    await expect(signIn).toHaveAttribute("data-preview-unwired", "true");
    await signIn.click();
    await expect(page).toHaveURL(`http://cuadrao.ai:${SITE_PORT}/`);
  } finally {
    await browser.close();
  }
});

async function attachMenuEvidence(page: Page, name: string) {
  execFileSync("git", ["diff", "--exit-code", "HEAD", "--", "marketing"]);
  await test.info().attach(`${name}.png`, { body: await page.screenshot(), contentType: "image/png" });
  await test.info().attach(`${name}-source.json`, {
    body: Buffer.from(JSON.stringify({
      commit: execFileSync("git", ["rev-parse", "HEAD"], { encoding: "utf8" }).trim(),
      tree: execFileSync("git", ["rev-parse", "HEAD^{tree}"], { encoding: "utf8" }).trim(),
      viewport: page.viewportSize(),
      menu: await page.locator("#business-mobile-menu").boundingBox(),
      scroll: await page.evaluate(() => window.scrollY),
      menuScroll: await page.locator("#business-mobile-menu").evaluate(node => node.scrollTop),
      route: new URL(page.url()).pathname,
    }, null, 2)),
    contentType: "application/json",
  });
}

for (const { home, cta, login } of cases) {
  test(`${home} phone menu covers the hero and keeps keyboard focus inside`, async ({ page }) => {
    test.skip(test.info().project.name !== "mobile", "phone menu coverage");
    await page.goto(home);
    const trigger = page.locator('header button[aria-controls="business-mobile-menu"]');
    const scroll = await page.evaluate(() => window.scrollY);
    const previousOverflow = await page.locator("body").evaluate(node => node.style.overflow);
    await trigger.click();
    const nav = page.locator("#business-mobile-menu");
    const box = (await nav.boundingBox())!;
    expect(Math.abs(box.y + box.height - page.viewportSize()!.height)).toBeLessThanOrEqual(1);
    const hero = (await page.locator("main").getByRole("link", { name: cta, exact: true }).first().boundingBox())!;
    const point = { x: hero.x + hero.width / 2, y: hero.y + hero.height / 2 };
    expect(point.y).toBeLessThan(page.viewportSize()!.height);
    expect(await page.evaluate(({ x, y }) => Boolean(document.elementFromPoint(x, y)?.closest("#business-mobile-menu")), point)).toBe(true);
    await expect(nav.getByRole("link", { name: cta, exact: true })).toHaveAttribute("href", "/contacto");
    await expect(page.locator("body")).toHaveCSS("overflow", "hidden");
    await attachMenuEvidence(page, "phone-menu-coverage");
    const last = nav.getByRole("button", { name: login, exact: true });
    await last.focus(); await page.keyboard.press("Tab"); await expect(trigger).toBeFocused();
    await page.keyboard.press("Shift+Tab"); await expect(last).toBeFocused();
    await page.keyboard.press("Escape");
    await expect(nav).toHaveCount(0); await expect(trigger).toBeFocused();
    expect(await page.locator("body").evaluate(node => node.style.overflow)).toBe(previousOverflow);
    expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
  });
}

test("short phone menu scrolls its links without scrolling the page and restores it on close", async ({ page }) => {
  test.skip(test.info().project.name !== "mobile", "short phone menu coverage");
  await page.setViewportSize({ width: 390, height: 420 });
  await page.goto("/en"); await page.evaluate(() => window.scrollTo(0, 600));
  const trigger = page.locator('header button[aria-controls="business-mobile-menu"]');
  const scroll = await page.evaluate(() => window.scrollY);
  await trigger.click();
  const nav = page.locator("#business-mobile-menu");
  const box = (await nav.boundingBox())!;
  expect(Math.abs(box.y + box.height - 420)).toBeLessThanOrEqual(1);
  const last = nav.getByRole("button", { name: "Log in", exact: true });
  await trigger.focus(); await page.keyboard.press("Shift+Tab");
  await expect(last).toBeFocused(); await expect(last).toBeInViewport({ ratio: 1 });
  const focus = await last.evaluate(node => {
    const css = getComputedStyle(node), bounds = node.getBoundingClientRect();
    return { bottom: bounds.bottom + parseFloat(css.outlineWidth) + parseFloat(css.outlineOffset), panel: node.closest("nav")!.getBoundingClientRect().bottom };
  });
  expect(focus.bottom).toBeLessThanOrEqual(focus.panel);
  expect(await nav.evaluate(node => node.scrollTop)).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
  await attachMenuEvidence(page, "short-phone-menu-scrolled");
  await page.keyboard.press("Escape"); await expect(nav).toHaveCount(0); await expect(trigger).toBeFocused();
  expect(await page.evaluate(() => window.scrollY)).toBe(scroll);
});

test("menu follows the existing CSS tablet boundary and restores background scroll", async ({ page }) => {
  test.skip(test.info().project.name !== "mobile", "responsive menu boundary");
  await page.goto("/");
  for (const width of [799, 800]) {
    await page.setViewportSize({ width, height: 900 });
    const trigger = page.getByRole("button", { name: "Abrir menú" }); await trigger.click();
    const nav = page.locator("#business-mobile-menu");
    const box = (await nav.boundingBox())!;
    expect(Math.abs(box.y + box.height - 900)).toBeLessThanOrEqual(1);
    await attachMenuEvidence(page, `tablet-menu-${width}`);
    await page.setViewportSize({ width: 801, height: 900 });
    await expect(nav).toHaveCount(0);
    await expect(page.locator("body")).not.toHaveCSS("overflow", "hidden");
    await expect(page.locator("header nav:visible")).toHaveCount(1);
  }
});
