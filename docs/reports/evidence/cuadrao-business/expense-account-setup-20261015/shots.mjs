// Run from web/ against `next dev` with NEXT_PUBLIC_MOCK_AUTH=true and NEXT_PUBLIC_ENABLE_SPANISH=true:
// OUT=<dir> BASE=http://localhost:<port> bun <copy of this file in web/>.ts
import { chromium } from "@playwright/test";
import { installBreakpointFixture } from "./e2e/support/breakpoint-fixture";

const base = process.env.BASE ?? "http://localhost:3617";
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
    await page.getByLabel("Nombre").fill("Caja chica");
    await page.getByLabel("Tipo de cuenta").selectOption("cash");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-2-filled.png` });
    await page.evaluate(() => { globalThis.__businessFixtureFailNextWrite = "service_unavailable"; });
    await page.getByRole("button", { name: "Añadir cuenta" }).click();
    await page.getByText("Ha ocurrido un error", { exact: true }).waitFor();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-3-error.png` });
    await page.getByRole("button", { name: "Añadir cuenta" }).click();
    await page.getByLabel("Pagado desde").waitFor();
    await page.getByTestId("record-expense-amount").fill("850");
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-4-added.png` });
    const chosen = await page.getByLabel("Pagado desde").inputValue();
    const saveEnabled = await page.getByRole("button", { name: "Guardar gasto" }).isEnabled();
    console.log(size, scheme, "chosen", chosen, "save enabled", saveEnabled);
    await page.close();
  }
}
await browser.close();
