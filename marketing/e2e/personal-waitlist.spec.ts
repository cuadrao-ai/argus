import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page }) => {
  await page.route("**/api/signups/config", (route) => route.fulfill({ json: { siteKey: "fixture-site-key" } }));
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js*", (route) => route.fulfill({
    contentType: "application/javascript",
    body: "window.turnstile={render:(_,o)=>{o.callback('fixture-token');return 'fixture';},remove:()=>{}};",
  }));
});

test("Spanish optional answers stay accessible and the unfinished endpoint fails closed", async ({ page }, info) => {
  await page.goto("/personal");
  await page.getByRole("textbox", { name: "Correo", exact: true }).fill("fixture@example.test");
  const methods = page.getByRole("combobox", { name: "¿Cómo llevas hoy tus gastos?" });
  await expect(methods.locator("option")).toHaveText(["", "No los llevo", "En una libreta o notas", "En Excel o Google Sheets", "En otra app", "Otra forma"]);
  await methods.selectOption("En una libreta o notas");
  await page.getByRole("textbox", { name: "¿Qué te gustaría que Cuadrao te resolviera?" }).fill("Ordenar mis gastos");
  await expect(page.getByText("No incluyas datos de cuentas o tarjetas.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "¿Es para tu negocio? Escríbenos" })).toHaveAttribute("href", "/contacto");
  await expect(page.locator("form #signup-privacy a")).toHaveAttribute("href", "/privacidad");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("personal-waitlist-form.png"), fullPage: true });
  const response = page.waitForResponse((result) => result.url().endsWith("/api/waitlist/signups"));
  await page.getByRole("button", { name: "Avísame cuando pueda probarla" }).click();
  expect((await response).status()).toBe(503);
  await expect(page.locator("#signup-error")).toBeVisible();
  await expect(page.locator("#personal-email")).toHaveValue("fixture@example.test");
});

test("digit warning is inline and the approved success sentence uses an explicit response fixture", async ({ page }, info) => {
  await page.route("**/api/waitlist/signups", (route) => route.fulfill({ json: { status: "registered" } }));
  await page.goto("/personal");
  await page.getByRole("textbox", { name: "Correo", exact: true }).fill("fixture@example.test");
  await page.getByRole("textbox", { name: "¿Qué te gustaría que Cuadrao te resolviera?" }).fill("Cuenta 1234 5678 9012");
  await expect(page.getByText("Quita los números de cuenta o tarjeta para enviar.", { exact: true })).toBeVisible();
  await page.getByRole("textbox", { name: "¿Qué te gustaría que Cuadrao te resolviera?" }).fill("Ordenar mis gastos");
  await page.getByRole("button", { name: "Avísame cuando pueda probarla" }).click();
  await expect(page.getByRole("heading", { name: "Te avisaremos cuando Cuadrao esté listo para ti." })).toBeFocused();
  await page.screenshot({ path: info.outputPath("personal-waitlist-confirmation-fixture.png"), fullPage: true });
  expect(await page.context().cookies()).toEqual([]);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
});
