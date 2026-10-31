import { AxeBuilder } from "@axe-core/playwright";
import { expect, test } from "@playwright/test";
import documents from "../content/legal-es.json";

for (const slug of Object.keys(documents) as (keyof typeof documents)[]) {
  for (const width of [320, 390]) {
    test(`${slug} at ${width}px preserves the cleared text and is accessible`, async ({ page }, info) => {
      await page.setViewportSize({ width, height: 844 });
      await page.emulateMedia({ reducedMotion: "reduce" });
      const response = await page.goto(`/${slug}`);
      expect(response?.status()).toBe(200);
      const omitsRobotsHeader = slug === "privacidad" || slug === "eliminar-datos";
      expect(response?.headers()["x-robots-tag"]).toBe(omitsRobotsHeader ? undefined : "noindex, nofollow");
      await page.evaluate(() => document.fonts.ready);
      const document = documents[slug];
      const expected = [document.title, ...document.blocks.flatMap((block) =>
        "items" in block && block.items ? block.items : block.text,
      )].join(" ").replaceAll("**", "").replace(/\s+/g, " ").trim()
        .replace(
          "Vigente desde: 15 de octubre de 2026 Última actualización: 16 de octubre de 2026",
          "Última actualización: 16 de octubre de 2026",
        );
      expect((await page.locator("article").innerText()).replace(/\s+/g, " ").trim()).toBe(expected);
      await expect(page.locator("main h1")).toHaveCount(1);
      expect(await page.locator("main h3, main h4, main h5, main h6").count()).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.locator('div[lang="es-DO"]')).toBeVisible();
      const audit = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa", "wcag21aa"]).analyze();
      expect(audit.violations.map((v) => `${v.id}: ${v.nodes.length}`)).toEqual([]);
      for (const name of ["Términos", "Privacidad", "hola@cuadrao.ai"]) {
        const link = page.locator("footer").getByRole("link", { name, exact: true });
        await expect(link).toBeVisible();
        const box = await link.boundingBox();
        expect(box!.height).toBeGreaterThanOrEqual(24);
        await link.focus();
        expect(await link.evaluate((node) => getComputedStyle(node).outlineStyle)).not.toBe("none");
      }
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: info.outputPath(`${slug}-${width}.png`), fullPage: true });
      await page.evaluate(() => { document.documentElement.style.zoom = "2"; });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.locator("main h1")).toBeVisible();
    });
  }
}

test("Spanish legal navigation opens each document and rejects Spanish slugs in English", async ({ page, request }) => {
  await page.goto("/privacidad");
  await page.locator("footer").getByRole("link", { name: "Términos", exact: true }).click();
  await expect(page).toHaveURL(/\/terminos$/);
  await page.locator("footer").getByRole("link", { name: "Eliminar tus datos", exact: true }).click();
  await expect(page).toHaveURL(/\/eliminar-datos$/);
  for (const path of ["/en/terminos", "/en/eliminar-datos"]) expect((await request.get(path)).status()).toBe(404);
});

for (const [path, title] of [["/en/privacy", "Privacy policy for the Cuadrao website"], ["/en/terms", "Cuadrao Website Terms of Use"], ["/en/delete-data", "Delete your data"]]) {
  test(`English source renders at ${path}`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("main h1")).toContainText(title);
    await expect(page.locator("article")).toContainText("October 16, 2026");
    await expect(page.locator("footer")).toContainText("© Cuadrao LLC 2026");
    await expect(page.locator("footer")).not.toContainText("Mountain Road");
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
}

for (const [path, tab, heading] of [
  ["/privacidad", "Privacidad | Cuadrao", "Política de privacidad del sitio web de Cuadrao"],
  ["/terminos", "Términos | Cuadrao", "Términos de uso del sitio web de Cuadrao"],
  ["/eliminar-datos", "Eliminar tus datos | Cuadrao", "Eliminar tus datos"],
  ["/en/privacy", "Privacy | Cuadrao", "Privacy policy for the Cuadrao website"],
  ["/en/terms", "Terms | Cuadrao", "Cuadrao Website Terms of Use"],
  ["/en/delete-data", "Delete your data | Cuadrao", "Delete your data"],
] as const) {
  test(`${path} puts the short title in the first HTML response and keeps the document heading`, async ({ page }) => {
    const response = await page.goto(path);
    const html = await response!.text();
    expect(html).toContain(`<title>${tab}</title>`);
    expect(html).toContain('src="/cuadrao-site/cuadrao-lockup-light.svg"');
    await expect(page).toHaveTitle(tab);
    await expect(page.locator("main h1")).toHaveText(heading);
    const logo = page.locator("header img[alt='cuadrao']");
    await expect(logo).toBeVisible();
    const box = await logo.boundingBox();
    expect(box!.width).toBeGreaterThan(40);
    expect(box!.height).toBeGreaterThan(16);
  });
}

test("the privacy logo and tab title are in the page when JavaScript is off", async ({ browser }) => {
  const context = await browser.newContext({
    javaScriptEnabled: false,
    viewport: { width: 1280, height: 800 },
  });
  try {
    const page = await context.newPage();
    const response = await page.goto("/privacidad");
    expect(await response!.text()).toContain("<title>Privacidad | Cuadrao</title>");
    await expect(page).toHaveTitle("Privacidad | Cuadrao");
    await expect(page.locator("header img[alt='cuadrao']")).toBeVisible();
  } finally {
    await context.close();
  }
});
