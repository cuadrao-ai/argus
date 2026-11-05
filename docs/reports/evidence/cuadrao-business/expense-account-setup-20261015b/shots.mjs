// Run from web/ against `next dev` with NEXT_PUBLIC_MOCK_AUTH=true and NEXT_PUBLIC_ENABLE_SPANISH=true:
// OUT=<dir> BASE=http://localhost:<port> bun <copy of this file in web/>.ts
import { chromium } from "@playwright/test";
import { installBreakpointFixture } from "./e2e/support/breakpoint-fixture";

const base = process.env.BASE ?? "http://localhost:3627";
const out = process.env.OUT;
const browser = await chromium.launch();
const sizes = { desktop: { width: 1280, height: 860 }, phone: { width: 390, height: 844 } };

for (const [size, viewport] of Object.entries(sizes)) {
  for (const scheme of ["light", "dark"]) {
    const page = await browser.newPage({ viewport, locale: "es-419", colorScheme: scheme, deviceScaleFactor: 1 });
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme: scheme, emptyChat: true });
    await page.goto(`${base}/dev/business-preview?accounts=none`);
    await page.getByRole("button", { name: "Registrar gasto" }).first().click();
    await page.getByRole("button", { name: "Añadir cuenta" }).waitFor();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-1-empty.png` });
    const empty = [await page.getByLabel("Nombre").inputValue(), await page.getByLabel("Tipo de cuenta").inputValue(), await page.getByLabel("Moneda").inputValue(), await page.getByRole("button", { name: "Añadir cuenta" }).isEnabled()];
    await page.getByLabel("Tipo de cuenta").selectOption("checking");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-2-filled.png` });
    await page.evaluate(() => { globalThis.__businessFixtureFailNextWrite = "service_unavailable"; });
    await page.getByRole("button", { name: "Añadir cuenta" }).click();
    await page.getByText("No pudimos crear la cuenta. Revisa el nombre e inténtalo de nuevo.", { exact: true }).waitFor();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-3-error.png` });
    await page.getByRole("button", { name: "Añadir cuenta" }).click();
    await page.getByLabel("Pagado desde").waitFor();
    await page.getByTestId("record-expense-amount").fill("850");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-4-added.png` });
    const chosen = await page.getByLabel("Pagado desde").locator("option:checked").textContent();
    console.log(size, scheme, "empty [name, type, currency, add enabled]", JSON.stringify(empty), "chosen", chosen);
    await page.close();
  }
}
await browser.close();
