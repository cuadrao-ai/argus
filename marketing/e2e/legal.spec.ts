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
      expect(response?.headers()["x-robots-tag"]).toBe("noindex, nofollow");
      await page.evaluate(() => document.fonts.ready);
      const document = documents[slug];
      const expected = [document.title, ...document.blocks.flatMap((block) =>
        "items" in block && block.items ? block.items : block.text,
      )].join(" ").replaceAll("**", "").replace(/\s+/g, " ").trim();
      expect((await page.locator("article").innerText()).replace(/\s+/g, " ").trim()).toBe(expected);
      await expect(page.locator("main h1")).toHaveCount(1);
      expect(await page.locator("main h3, main h4, main h5, main h6").count()).toBe(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await expect(page.locator('div[lang="es-419"]')).toBeVisible();
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

test("Spanish legal navigation opens each document and adds no English routes", async ({ page, request }) => {
  await page.goto("/privacidad");
  await page.locator("footer").getByRole("link", { name: "Términos", exact: true }).click();
  await expect(page).toHaveURL(/\/terminos$/);
  await page.locator("footer").getByRole("link", { name: "Eliminar tus datos", exact: true }).click();
  await expect(page).toHaveURL(/\/eliminar-datos$/);
  for (const path of ["/en/terminos", "/en/eliminar-datos"]) expect((await request.get(path)).status()).toBe(404);
});
