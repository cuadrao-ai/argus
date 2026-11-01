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
  test("keeps both actions clickable above the scene", async ({ page }) => {
    await page.goto(PATH);
    const cta = page.getByRole("main").getByRole("link", { name: "Hablemos de tu negocio" });
    await cta.click({ position: { x: 40, y: 4 }, trial: true });
    await page.getByRole("main").getByRole("link", { name: "Ver cómo funciona" }).click({ trial: true });
  });

  test("passes an accessibility scan", async ({ page }) => {
    await page.goto(PATH);
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

test.describe("preview header", () => {
  test("reads language, sign in, then the button", async ({ page, isMobile }) => {
    test.skip(isMobile, "phones use the menu");
    await page.goto(PATH);
    const nav = page.getByRole("navigation").first();
    await expect(nav.getByRole("link", { name: "Business" })).toHaveCount(0);
    await expect(nav.locator("a, button")).toHaveText(["English", "Iniciar sesión", "Hablemos de tu negocio"]);
  });
});
