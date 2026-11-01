import AxeBuilder from "@axe-core/playwright";
import { expect, test, type Page } from "@playwright/test";

import { PUBLIC_URL } from "./ports";

const PATH = "/es/vista-previa";

const frame = (page: Page) => page.locator("[data-scene-frame]");

async function seek(page: Page, p: number): Promise<void> {
  await page.evaluate((progress) => {
    const scene = document.querySelector("[data-scene-frame]")?.closest("section");
    if (!scene) throw new Error("scene missing");
    const top = scene.getBoundingClientRect().top + window.scrollY;
    window.scrollTo({ top: top + (scene.offsetHeight - window.innerHeight) * progress, behavior: "instant" });
  }, p);
}

test.describe("hidden preview", () => {
  test("is noindexed and unlisted on a private host", async ({ request }) => {
    const response = await request.get(PATH);
    expect(response.status()).toBe(200);
    expect(response.headers()["x-robots-tag"]).toContain("noindex");
    expect(await (await request.get("/sitemap.xml")).text()).not.toContain(PATH);
  });

  test("does not exist on the public host", async ({ request }) => {
    expect((await request.get(`${PUBLIC_URL}${PATH}`)).status()).toBe(404);
  });

  test("does not exist under the public domain name", async ({ request }) => {
    const response = await request.get(PATH, { headers: { "x-forwarded-host": "cuadrao.ai" } });
    expect(response.status()).toBe(404);
  });

  test("has no English page yet", async ({ request }) => {
    expect((await request.get("/en/vista-previa")).status()).toBe(404);
  });
});

test.describe("hero", () => {
  test("every in-page link has a target", async ({ page }) => {
    await page.goto(PATH);
    const missing = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLAnchorElement>('main a[href^="#"]')]
        .map((link) => link.hash.slice(1))
        .filter((id) => !document.getElementById(id)),
    );
    expect(missing).toEqual([]);
  });

  test("keeps both actions clickable above the scene", async ({ page }) => {
    await page.goto(PATH);
    const cta = page.getByRole("main").getByRole("link", { name: "Hablemos de tu negocio" });
    await cta.click({ position: { x: 40, y: 4 }, trial: true });
    await page.getByRole("main").getByRole("link", { name: "Ver cómo funciona" }).click({ trial: true });
  });

  test("passes an accessibility scan", async ({ page }) => {
    await page.goto(PATH);
    await expect(page.locator("[data-chat-photo]")).toHaveCSS("opacity", "0");
    const { violations } = await new AxeBuilder({ page }).analyze();
    expect(violations.map((violation) => violation.id)).toEqual([]);
  });
});

test.describe("product scene", () => {
  test("follows the scroll forward and backward", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones show the finished picture");
    await page.goto(PATH);
    await expect(page.locator("[data-scene-island]")).toHaveText("Esperando facturas");
    await expect(page.locator("[data-scene-count]")).toHaveText("4");

    await seek(page, 0.58);
    await expect(page.locator("[data-scene-island]")).toHaveText("Listo para revisar");
    await expect(page.locator("[data-scene-count]")).toHaveText("5");
    await expect(page.locator("[data-scene-invoice]")).toHaveText("Listo para revisar");

    await seek(page, 1);
    await expect(page.locator("[data-scene-export]")).toHaveText("Exportado");

    await seek(page, 0);
    await expect(page.locator("[data-scene-island]")).toHaveText("Esperando facturas");
    await expect(page.locator("[data-scene-export]")).toHaveText("Exportar 606 y 607");
  });

  test("shows the campaign day until it passes", async ({ page }) => {
    await page.clock.setFixedTime(new Date(2026, 10, 1, 9));
    await page.goto(PATH);
    await expect(page.locator("[data-scene-date]")).toContainText("domingo, 15 de noviembre");
  });

  test("follows today after the campaign day", async ({ page }) => {
    await page.clock.setFixedTime(new Date(2027, 0, 20, 9));
    await page.goto(PATH);
    await expect(page.locator("[data-scene-date]")).toContainText("miércoles, 20 de enero");
  });

  test("shows the finished picture with motion off", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    await page.goto(new URL(PATH, test.info().project.use.baseURL).href);
    await expect(page.locator("[data-scene-export]")).toHaveText("Exportado");
    const position = await frame(page).evaluate((node) => getComputedStyle(node.parentElement!).position);
    expect(position).toBe("static");
    await context.close();
  });

  test("fits a phone with no sideways scroll", async ({ page, isMobile }) => {
    test.skip(!isMobile, "phone layout");
    await page.goto(PATH);
    await expect(page.locator("[data-scene-export]")).toBeAttached();
    const widths = await page.evaluate(() => [document.documentElement.scrollWidth, window.innerWidth]);
    expect(widths[0]).toBe(widths[1]);
    const frameWidth = await frame(page).evaluate((node) => node.getBoundingClientRect().width);
    expect(frameWidth).toBe(widths[1] - 24);
  });
});

async function seekTo(page: Page, selector: string, p: number): Promise<void> {
  await page.evaluate(
    ([target, progress]) => {
      const box = document.querySelector(target as string) as HTMLElement;
      const top = box.getBoundingClientRect().top + window.scrollY;
      window.scrollTo({ top: top + (box.offsetHeight - window.innerHeight) * (progress as number), behavior: "instant" });
    },
    [selector, p],
  );
}

const TRACK = "[data-steps-track]";
const step = (page: Page) => page.locator('[aria-current="step"]');

test.describe("problem cards", () => {
  test("swap the title once the cards line up", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones skip this section");
    await page.goto(PATH);
    const before = page.getByRole("heading", { name: "Tus facturas están en todas partes." }).locator("..");
    const after = page.getByRole("heading", { name: "Ahora todo cuadra." }).locator("..");
    await seekTo(page, "#problema", 0.05);
    await expect(before).toHaveCSS("opacity", "1");
    await expect(after).toHaveCSS("opacity", "0");
    await seekTo(page, "#problema", 1);
    await expect(before).toHaveCSS("opacity", "0");
    await expect(after).toHaveCSS("opacity", "1");
  });

  test("stay out of the phone view", async ({ page, isMobile }) => {
    test.skip(!isMobile, "phone layout");
    await page.goto(PATH);
    await expect(page.locator("#problema")).toBeHidden();
  });
});

test.describe("how it works", () => {
  test("follows the scroll through all four steps", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones list the steps");
    await page.goto(PATH);
    for (const [share, name] of [
      [0.1, "Recibir"],
      [0.5, "Cuadrar"],
      [0.7, "Exportar"],
      [0.9, "Facturar"],
    ] as const) {
      await seekTo(page, TRACK, share);
      await expect(step(page)).toHaveText(name);
    }
  });

  test("plays the chat in order and rewinds it", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones play the chat by position");
    await page.goto(PATH);
    await seekTo(page, TRACK, 0);
    await expect(page.locator("[data-chat-reply]")).toHaveCount(0);
    await seekTo(page, TRACK, 0.2);
    await expect(page.locator("[data-chat-status]")).toHaveText("escribiendo...");
    await seekTo(page, TRACK, 0.36);
    await expect(page.locator("[data-chat-reply]")).toContainText("Factura recibida");
    await expect(page.locator("[data-chat-date]")).toHaveText("15-11-2026");
    await seekTo(page, TRACK, 0);
    await expect(page.locator("[data-chat-reply]")).toHaveCount(0);
  });

  test("the dock keeps the unfinished step out of the links", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones hide the dock");
    await page.goto(PATH);
    const soon = page.getByRole("img", { name: "Facturar · En preparación" });
    await expect(soon).toHaveCount(1);
    await expect(page.getByRole("link", { name: "Facturar · En preparación" })).toHaveCount(0);
  });

  test("a step title and a dock button jump to their step", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones have no jumps");
    await page.goto(PATH);
    await seekTo(page, TRACK, 0.1);
    await page.getByRole("button", { name: "Exportar" }).click();
    await expect(step(page)).toHaveText("Exportar");
    await seekTo(page, "section:has([data-scene-frame])", 0.5);
    await page.getByRole("link", { name: "Cuadrar" }).click();
    await expect(step(page)).toHaveText("Cuadrar");
  });

  test("shows the finished chat with motion off", async ({ browser }) => {
    const context = await browser.newContext({ reducedMotion: "reduce", viewport: { width: 1280, height: 800 } });
    const page = await context.newPage();
    await page.goto(new URL(PATH, test.info().project.use.baseURL).href);
    await expect(page.locator("[data-chat-reply]")).toContainText("Factura recibida");
    await context.close();
  });

  test("the phone shows the chat and all four steps", async ({ page, isMobile }) => {
    test.skip(!isMobile, "phone layout");
    await page.goto(PATH);
    await page.locator("#como").scrollIntoViewIfNeeded();
    await page.locator("[data-phone]").scrollIntoViewIfNeeded();
    await expect(page.locator("[data-chat-photo]")).toBeVisible();
    await expect(page.getByText("Lo aprobado sale en el 606 y el 607, listo para tu contable.")).toBeVisible();
  });

  test("passes an accessibility scan on a data panel", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones show the chat panel only");
    await page.goto(PATH);
    await seekTo(page, TRACK, 0.5);
    await expect(step(page)).toHaveText("Cuadrar");
    const panel = page.locator('[data-step-panel="1"]');
    await expect(panel.locator("> div").last()).toHaveCSS("opacity", "1");
    await expect(panel.getByText("Listo").nth(1)).toHaveCSS("opacity", "1");
    const { violations } = await new AxeBuilder({ page }).include("#como").analyze();
    expect(violations.map((violation) => violation.id)).toEqual([]);
  });
});

const question = (page: Page, name: string) => page.getByRole("button", { name });

test.describe("faq", () => {
  test("opens the first answer on load, so the examples note shows", async ({ page }) => {
    await page.goto(PATH);
    await expect(question(page, "¿Ya puedo usar Cuadrao para mi negocio?")).toHaveAttribute("aria-expanded", "true");
    await expect(page.getByText("funciones previstas con datos ficticios")).toBeVisible();
  });

  test("keeps one answer open at a time", async ({ page }) => {
    await page.goto(PATH);
    await question(page, "¿Cuánto va a costar?").click();
    await expect(page.getByText("Aún no hemos definido los precios.")).toBeVisible();
    await expect(page.getByText("funciones previstas con datos ficticios")).toBeHidden();
    await expect(page.locator('[id="preguntas"] [aria-expanded="true"]')).toHaveCount(1);
  });

  test("closes the open answer when its question is clicked again", async ({ page }) => {
    await page.goto(PATH);
    await question(page, "¿Ya puedo usar Cuadrao para mi negocio?").click();
    await expect(page.locator('[id="preguntas"] [aria-expanded="true"]')).toHaveCount(0);
  });

  test("works from the keyboard", async ({ page }) => {
    await page.goto(PATH);
    await question(page, "¿Qué límites debo conocer?").focus();
    await page.keyboard.press("Enter");
    await expect(page.getByText("Estamos preparando la emisión de e-CF")).toBeVisible();
  });

  test("keeps a clicked question out from under the header", async ({ page, isMobile }) => {
    test.skip(!isMobile, "long answers push hardest on a phone");
    await page.goto(PATH);
    await question(page, "¿Para quién es y en qué ayudará?").click();
    await expect(page.getByText("Para pequeños y medianos negocios")).toBeVisible();
    const next = question(page, "¿Cuánto va a costar?");
    await next.evaluate((node) => {
      window.scrollBy({ top: node.getBoundingClientRect().top - 90, behavior: "instant" });
    });
    await next.click();
    await expect(page.getByText("Aún no hemos definido los precios.")).toBeVisible();
    await page.waitForTimeout(500);
    const top = await next.evaluate((node) => node.getBoundingClientRect().top);
    expect(top).toBeGreaterThanOrEqual(80);
  });
});

test.describe("closing sections", () => {
  test("the ledger closes the month before the scene date", async ({ page }) => {
    await page.clock.setFixedTime(new Date(2026, 11, 3, 9));
    await page.goto(PATH);
    await expect(page.locator("[data-ledger-month]")).toHaveText("606 · Noviembre");
  });

  test("the footer links reach sections on this page", async ({ page }) => {
    await page.goto(PATH);
    for (const name of ["Ver cómo funciona", "Preguntas frecuentes", "Nosotros"]) {
      const href = await page.getByRole("contentinfo").getByRole("link", { name }).getAttribute("href");
      const id = href?.split("#")[1];
      await expect(page.locator(`[id="${id}"]`)).toHaveCount(1);
    }
  });

  test("the footer credit stays reachable by the pointer", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones hide the credit reveal");
    await page.goto(PATH);
    const credits = page.locator("[data-footer-credits]");
    await credits.scrollIntoViewIfNeeded();
    await credits.hover();
    await expect(credits.getByText("Hecho con ♥ para la República Dominicana")).toBeVisible();
  });

  test("a phone drops the check list and keeps the ledger", async ({ page, isMobile }) => {
    test.skip(!isMobile, "phone layout");
    await page.goto(PATH);
    await expect(page.getByText("606 y 607 salen de registros revisados")).toBeHidden();
    await expect(page.locator("[data-ledger-month]")).toBeVisible();
  });
});

test.describe("preview header", () => {
  test("reads language, sign in, then the button", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones use the menu");
    await page.goto(PATH);
    const nav = page.getByRole("navigation").first();
    await expect(nav.getByRole("link", { name: "Business" })).toHaveCount(0);
    await expect(nav.locator("a, button")).toHaveText(["English", "Iniciar sesión", "Hablemos de tu negocio"]);
  });
});
