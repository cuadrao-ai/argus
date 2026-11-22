import { expect, test } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

test.beforeEach(async ({ page }) => {
  await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
});

for (const tab of ["listos", "all", "attention", "eliminados"]) {
  test(`${tab} survives reload and a shared link`, async ({ page, context }) => {
    await page.goto("/dev/business-preview?view=inbox&inbox=empty");
    if (tab === "all") await page.locator("#reception-tab-listos").click();
    await page.locator(`#reception-tab-${tab}`).click();
    await expect(page.locator(`#reception-tab-${tab}`)).toHaveAttribute("aria-selected", "true");
    await page.reload();
    await expect(page.locator(`#reception-tab-${tab}`)).toHaveAttribute("aria-selected", "true");
    await expect(page.getByTestId("reception-empty")).toBeVisible();
    expect(new URL(page.url()).searchParams.get("receptionView")).toBe(tab);
    expect(new URL(page.url()).searchParams.get("inbox")).toBe("empty");
    if (process.env.RECEPTION_CAPTURE) {
      const evidence = resolve(__dirname, "../../temp/2353-evidence");
      await mkdir(evidence, { recursive: true });
      await page.screenshot({ path: `${evidence}/${process.env.RECEPTION_CAPTURE}-${tab}.png`, animations: "disabled" });
    }
    const shared = await context.newPage();
    await shared.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    await installBreakpointFixture(shared, { language: "es-419", theme: "light", emptyChat: true });
    await shared.goto(page.url());
    await expect(shared.locator(`#reception-tab-${tab}`)).toHaveAttribute("aria-selected", "true");
    await shared.close();
  });
}

for (const value of ["", "unknown"]) test(`missing or unknown tab falls back to Todos (${value})`, async ({ page }) => {
  await page.goto(`/dev/business-preview?view=inbox&receptionView=${value}`);
  await expect(page.locator("#reception-tab-all")).toHaveAttribute("aria-selected", "true");
});

test("choosing a tab adds no history entry", async ({ page }) => {
  await page.goto("/dev/business-preview?view=inbox");
  const entries = await page.evaluate(() => window.history.length);
  await page.locator("#reception-tab-listos").click();
  await page.locator("#reception-tab-attention").click();
  await expect(page.locator("#reception-tab-attention")).toHaveAttribute("aria-selected", "true");
  expect(new URL(page.url()).searchParams.get("receptionView")).toBe("attention");
  expect(await page.evaluate(() => window.history.length)).toBe(entries);
});

test("closing a dossier preserves its Listos tab", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dev/business-preview?view=inbox");
  await page.locator("#reception-tab-listos").click();
  await page.getByTestId("reception-row").first().getByRole("button", { name: "Abrir", exact: true }).click();
  await expect(page.getByTestId("side-drawer")).toBeVisible();
  await page.getByTestId("side-drawer").getByRole("button", { name: "Cerrar", exact: true }).click();
  await expect(page.getByTestId("side-drawer")).toHaveCount(0);
  await expect(page.locator("#reception-tab-listos")).toHaveAttribute("aria-selected", "true");
  expect(new URL(page.url()).searchParams.get("receptionView")).toBe("listos");
});

test("another screen drops the tab, so the Bandeja opens on Todos again", async ({ page }) => {
  await page.setViewportSize({ width: 1440, height: 900 });
  await page.goto("/dev/business-preview?view=inbox");
  await page.locator("#reception-tab-listos").click();
  const nav = page.getByTestId("business-sidebar-nav");
  await nav.getByRole("button", { name: /Registros/ }).click();
  await expect(page).toHaveURL(/view=transactions/);
  expect(new URL(page.url()).searchParams.has("receptionView")).toBe(false);
  await nav.getByRole("button", { name: /Bandeja/ }).click();
  await expect(page.locator("#reception-tab-all")).toHaveAttribute("aria-selected", "true");
});
