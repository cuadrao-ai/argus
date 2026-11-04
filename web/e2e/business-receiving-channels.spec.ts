import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

async function setup(page: Page, available: boolean, history = false) {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const requests: string[] = [];
  const historyRequests: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false });
  await page.route("**/api/v1/whatsapp/**", route => {
    requests.push(new URL(route.request().url()).pathname);
    return route.fulfill({ status: 404, json: { code: "whatsapp_unavailable" } });
  });
  await page.route("**/api/v1/business/**", async route => {
    const path = new URL(route.request().url()).pathname.split("/business/")[1];
    const historicalRead = route.request().method() === "GET" && /^email\/(deliveries(?:\/[^/]+)?|inbox)$/.test(path);
    if (historicalRead) historyRequests.push(path);
    else if (path.startsWith("email")) requests.push(path);
    if (path === "workspace") return route.fulfill({ json: { ...await source.workspace(), receiving_channels: { email: { available }, whatsapp: { available: false } } } });
    if (path === "space") return route.fulfill({ json: { id: "fixture-space", name: "Colmado de prueba" } });
    if (path === "spaces") return route.fulfill({ json: { spaces: (await source.spaces()).slice(0, 1) } });
    if (path === "overview") return route.fulfill({ json: await source.overview("2026-10-01", "2026-10-31") });
    if (path === "receipts") return route.fulfill({ json: { items: history ? [{ ...await source.receipt("rcpt-ferreteria"), draft_id: null, channel: "email", email_delivery_ids: ["email-ferreteria"] }] : [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, needs_attention_count: 0, ready_to_review_count: 0, bandeja_attention_count: 0, bandeja_listo_count: 0 } } });
    if (path === "receipt-reading") return route.fulfill({ json: { enabled: false, available: true, can_change: false } });
    if (path === "email") return route.fulfill({ json: { enabled: false, receiving_address: null } });
    if (path === "receipts/rcpt-ferreteria") return route.fulfill({ json: { ...await source.receipt("rcpt-ferreteria"), draft_id: null, channel: "email", email_delivery_ids: ["email-ferreteria"] } });
    if (path === "receipts/rcpt-ferreteria/source") {
      const blob = await source.receiptSource("rcpt-ferreteria");
      return route.fulfill({ contentType: blob.type, body: Buffer.from(await blob.arrayBuffer()) });
    }
    if (path === "email/deliveries") return route.fulfill({ json: { items: history ? await source.emailDeliveries() : [] } });
    if (path === "email/deliveries/email-ferreteria") return route.fulfill({ json: await source.emailDelivery("email-ferreteria") });
    if (["email/senders", "captures"].includes(path)) return route.fulfill({ json: { items: [] } });
    if (path === "consent") return fulfillAcceptedBusinessConsent(route);
    return route.fulfill({ status: 404, json: { code: "fixture_only" } });
  });
  return { requests, historyRequests, errors };
}

for (const width of [1440, 390]) {
  test(`unavailable channels have no intake offers or requests at ${width}px`, async ({ page }, info) => {
    const observed = await setup(page, false);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/biz?view=inbox");
    await expect(page.getByTestId("reception-preview")).toBeVisible();
    await expect(page.getByRole("tab", { name: /^Listos\s*0$/ })).toBeVisible();
    await expect(page.getByText("o recibe documentos por correo", { exact: false })).toHaveCount(0);
    await expect(page.getByTestId("email-address")).toHaveCount(0);
    await page.screenshot({ path: info.outputPath(`channels-off-inbox-${width}.png`), fullPage: true });
    await page.getByRole("button", { name: "Filtros", exact: true }).click();
    if (width < 720) await page.getByRole("button", { name: "Canal", exact: true }).click();
    await expect(page.getByText("Carga manual", { exact: true })).toBeVisible();
    await expect(page.getByText("Correo", { exact: true })).toBeVisible();
    await expect(page.getByText("WhatsApp", { exact: true })).toBeVisible();
    await page.goto("/biz?view=business&tab=correo");
    await expect(page.getByTestId("business-settings")).toBeVisible();
    await expect(page.getByRole("button", { name: "Obtener una dirección" })).toHaveCount(0);
    await expect(page.getByText("Remitentes", { exact: true })).toHaveCount(0);
    expect(observed.requests).toEqual([]);
    expect(observed.errors).toEqual([]);
    await page.screenshot({ path: info.outputPath(`channels-off-reception-${width}.png`), fullPage: true });
  });

  test(`an email receipt opens its original email while receiving is off at ${width}px`, async ({ page }, info) => {
    const observed = await setup(page, false, true);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/biz?receipt=rcpt-ferreteria");
    if (width < 720) await page.getByTestId("receipt-review-tabs").getByRole("radio", { name: "Original", exact: true }).click();
    await page.getByTestId("receipt-see-email").click();
    const message = "Buenas tardes, adjunto la factura de hoy. Gracias por su compra.";
    await expect(page.getByTestId("email-record")).toBeVisible();
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    expect(observed.historyRequests).toContain("email/deliveries/email-ferreteria");
    expect(observed.requests).toEqual([]);
    await page.screenshot({ path: info.outputPath(`channels-history-off-${width}.png`), fullPage: true });
    await page.goto("/biz?email=email-ferreteria");
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    expect(observed.requests).toEqual([]);
    expect(observed.errors).toEqual([]);
  });

  test(`available email without an address offers setup at ${width}px`, async ({ page }, info) => {
    const observed = await setup(page, true);
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/biz?view=business&tab=correo");
    await expect(page.getByRole("button", { name: "Obtener una dirección" })).toBeVisible();
    await expect(page.getByText("Remitentes", { exact: true })).toBeVisible();
    expect(observed.requests).toContain("email");
    expect(observed.requests.filter(path => path.includes("whatsapp"))).toEqual([]);
    expect(observed.errors).toEqual([]);
    await page.screenshot({ path: info.outputPath(`channels-setup-${width}.png`), fullPage: true });
  });
}
