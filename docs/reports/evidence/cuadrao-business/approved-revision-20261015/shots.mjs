// Run from web/ against `next dev` with NEXT_PUBLIC_MOCK_AUTH=true and NEXT_PUBLIC_ENABLE_SPANISH=true:
// OUT=<dir> BASE=http://localhost:<port> bun <copy of this file in web/>.ts
import { chromium } from "@playwright/test";
import { installBreakpointFixture } from "./e2e/support/breakpoint-fixture";

const base = process.env.BASE ?? "http://localhost:3721";
const out = process.env.OUT;
const browser = await chromium.launch();
const sizes = { desktop: { width: 1280, height: 860 }, phone: { width: 390, height: 844 } };

for (const [size, viewport] of Object.entries(sizes)) {
  for (const scheme of ["light", "dark"]) {
    const page = await browser.newPage({ viewport, locale: "es-419", colorScheme: scheme, deviceScaleFactor: 1 });
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort("blockedbyclient"));
    await installBreakpointFixture(page, { language: "es-419", theme: scheme, emptyChat: true });

    await page.goto(`${base}/dev/business-preview?draft=10000000-0000-4000-8000-000000000015`);
    const status = page.getByRole("status").filter({ hasText: "Registrado el" });
    await status.waitFor();
    await status.scrollIntoViewIfNeeded();
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-1-recorded-after-mark.png` });
    console.log(size, scheme, "recorded", await status.innerText(), "header", await page.getByText(/^Revisión \d+$/).first().innerText());

    await page.goto(`${base}/dev/business-preview?view=inbox`);
    await page.locator('[data-testid="business-inbox-receipts"] button').filter({ hasText: "Ferretería La Esquina" }).click();
    await page.getByLabel("Pagado desde").selectOption({ index: 1 });
    await page.getByRole("button", { name: "Guardar detalles de revisión" }).click();
    await page.getByRole("button", { name: "Aprobar y siguiente" }).click();
    await page.waitForFunction(() => document.activeElement?.id === "receipt-review-title" && !location.search.includes("rcpt-ferreteria"), null, { timeout: 15000 }).catch(() => undefined);
    await page.waitForTimeout(500);
    await page.screenshot({ path: `${out}/${size}-${scheme}-2-next-heading-focused.png` });
    console.log(size, scheme, "focused", await page.evaluate(() => `${document.activeElement?.id}: ${document.activeElement?.textContent}`));
    await page.close();
  }
}
await browser.close();
