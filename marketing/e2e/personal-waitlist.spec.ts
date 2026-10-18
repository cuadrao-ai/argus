import { asNewClient, mockState, resetMock } from "./support";
import { mockWaitlistWidget } from "./waitlist-fixture";
import { expect, test } from "@playwright/test";

test.beforeEach(async ({ page, request, context }, info) => {
  await resetMock(request);
  await asNewClient(context, info);
  await mockWaitlistWidget(page);
});

test("Spanish optional answers stay accessible and missing runtime configuration fails closed", async ({ page }, info) => {
  await page.route("**/api/waitlist/signups", (route) => route.fulfill({ status: 503, json: { error: "unavailable" } }));
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
  await expect(page.getByRole("heading", { name: "Revisa tu correo." })).toBeFocused();
  await page.screenshot({ path: info.outputPath("personal-waitlist-confirmation-fixture.png"), fullPage: true });
  expect(await page.context().cookies()).toEqual([]);
  expect(await page.evaluate(() => [localStorage.length, sessionStorage.length])).toEqual([0, 0]);
});

test("scanner GETs preserve signup state and approved POST buttons confirm and remove", async ({ page, request }, info) => {
  await page.goto("/personal");
  await page.locator("#personal-email").fill("flow@example.test");
  await page.getByRole("button", { name: "Avísame cuando pueda probarla" }).click();
  await expect(page.getByRole("heading", { name: "Revisa tu correo." })).toBeVisible();
  const first = await mockState(request);
  expect(first.signups).toHaveLength(1); expect(first.emails).toHaveLength(1);
  const confirmation = first.emails[0].text.match(/https:\/\/cuadrao\.example\.test\/api\/waitlist\/confirm\?token=\S+/)![0];
  const confirmationPath = new URL(confirmation).pathname + new URL(confirmation).search;
  await page.goto(confirmationPath);
  await expect(page.locator("main > p")).toHaveText("Confirma que quieres recibir noticias de Cuadrao en este correo.");
  await expect(page.getByRole("button", { name: "Confirmar", exact: true })).toBeVisible();
  expect((await mockState(request)).signups[0].confirmed_at).toBeNull();
  expect((await mockState(request)).emails).toHaveLength(1);
  await page.screenshot({ path: info.outputPath("waitlist-confirm-button.png"), fullPage: true });
  const confirmationPost = page.waitForRequest((result) => result.url().includes(confirmationPath) && result.method() === "POST");
  await page.getByRole("button", { name: "Confirmar", exact: true }).click();
  await confirmationPost;
  await expect(page.getByRole("heading", { name: "Ya estás en la lista." })).toBeVisible();
  await page.screenshot({ path: info.outputPath("waitlist-confirmed.png"), fullPage: true });
  expect((await mockState(request)).emails).toHaveLength(2);
  await page.goto(confirmationPath);
  expect((await mockState(request)).emails).toHaveLength(2);
  const leave = first.emails[0].text.match(/https:\/\/cuadrao\.example\.test\/api\/waitlist\/leave\?token=\S+/)![0];
  const leavePath = new URL(leave).pathname + new URL(leave).search;
  await page.goto(leavePath);
  await expect(page.getByRole("button", { name: "Salir de la lista", exact: true })).toBeVisible();
  expect((await mockState(request)).signups).toHaveLength(1);
  expect((await mockState(request)).emails).toHaveLength(2);
  await page.screenshot({ path: info.outputPath("waitlist-leave-button.png"), fullPage: true });
  const leavePost = page.waitForRequest((result) => result.url().includes(leavePath) && result.method() === "POST");
  await page.getByRole("button", { name: "Salir de la lista", exact: true }).click();
  await leavePost;
  expect((await mockState(request)).signups).toHaveLength(0);
  await expect(page.getByRole("heading", { name: "Ya saliste de la lista." })).toBeVisible();
  await expect(page.getByText("Borramos tu correo y tus respuestas.")).toBeVisible();
  await page.screenshot({ path: info.outputPath("waitlist-left.png"), fullPage: true });
  expect((await request.post(leavePath, { form: { "List-Unsubscribe": "One-Click" } })).status()).toBe(200);
  expect((await mockState(request)).signups).toHaveLength(0);
});

test("the legacy public signup URL cannot bypass CAPTCHA", async ({ request }) => {
  const response = await request.post("/api/signups", { data: { email: "bypass@example.test", locale: "es" } });
  expect(response.status()).toBe(400);
  expect((await mockState(request)).signups).toHaveLength(0);
  expect((await mockState(request)).emails).toHaveLength(0);
});
