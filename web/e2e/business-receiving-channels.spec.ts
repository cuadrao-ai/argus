import { whatsappDisclosure } from "../__tests__/fixtures/whatsapp-disclosure";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

async function setup(page: Page, available: boolean, history = false, language: "es-419" | "en" = "es-419") {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const requests: string[] = [];
  const historyRequests: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme: "light", emptyChat: true });
  const source = createFixtureBusinessDataSource({ chatAvailable: false, receiptReading: { can_change: false } });
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
    if (path === "receipts") return route.fulfill({ json: { items: history ? [{ ...await source.receipt("rcpt-ferreteria"), draft_id: null, channel: "email", email_delivery_ids: ["email-ferreteria"] }] : [], activity: { reading_count: 0, unread_count: 0, presentation: "none", pending_review_count: 0, ready_to_review_count: 0, bandeja_attention_count: 0, bandeja_listo_count: 0 } } });
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
    await expect(page.getByRole("checkbox", { name: "Carga web", exact: true })).toBeVisible();
    await expect(page.getByRole("checkbox", { name: "Correo", exact: true })).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "WhatsApp", exact: true })).toHaveCount(0);
    await expect(page.getByRole("checkbox", { name: "Escrito aquí", exact: true })).toHaveCount(0);
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
    if (width < 720) await page.getByRole("tab", { name: "Documento", exact: true }).click();
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

for (const { width, language } of [
  { width: 1440, language: "es-419" }, { width: 390, language: "es-419" },
  { width: 1440, language: "en" }, { width: 390, language: "en" },
] as const) {
  test(`link a number from account settings in ${language} at ${width}px`, async ({ page }, info) => {
    const words = (language === "en" ? english : spanish).settings.whatsapp;
    await setup(page, false, false, language);
    await page.route((url) => url.pathname.endsWith("/api/v1/whatsapp/link") && url.searchParams.get("language") === language, route => route.fulfill({
      json: { ...whatsappDisclosure[language], linked: false, receiving_businesses: [{ space_id: "elsewhere", name: "Negocio de prueba" }], held_count: 0 },
    }));
    const message = "CUADRAO K7P2M9XQ";
    const url = "https://wa.me/15550100000?text=" + encodeURIComponent(message);
    // QR image for this synthetic one-tap link.
    const qr = "data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAEoAAABKAQAAAAA0q//cAAAAw0lEQVR42rWSMWqFQQiEJdsueBXBVvDqC7bCXkWw/cH3UoQQTZlYLR/DMI4L9TUH/vYJK+AS6PmA7ylN08xqlLg4cw2qar9Q3DKoZtn0hcXMI0NVMn+G/EHxXDfFRl1vPkKNnmBi0U4LOf02SnmDTk9meHOH9C0iHdOagzhy7WzaMHfErgUNFqOmxXcCN+xNSj2JfQulTRdodMYWox1Yawuv7pD7fTnpPbDnA3tc08nrDHohAoYvahwbN8bAp2f4n1/9AjM6QEty097jAAAAAElFTkSuQmCC";
    await page.route("**/api/v1/whatsapp/link-codes", route => route.fulfill({
      status: 201,
      json: {
        code: "K7P2M9XQ", message_text: message, expires_at: new Date(Date.now() + 600000).toISOString(),
        wa_me_url: url, qr_data_url: qr,
      },
    }));
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/biz?view=inbox");
    await page.getByTestId("header-profile-trigger").click();
    await page.getByTestId("profile-menu-settings").click();
    await page.getByRole("button", { name: "WhatsApp", exact: true }).click();
    const link = page.getByRole("button", { name: words.link_phone });
    await expect(link).toBeVisible();
    await expect(page.getByText(whatsappDisclosure[language].disclosure, { exact: true })).toBeVisible();
    await page.screenshot({ path: info.outputPath(`whatsapp-ready-${language}-${width}.png`) });
    const issued = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith("/whatsapp/link-codes") && request.method() === "POST");
    await link.click();
    expect((await issued).postDataJSON()).toEqual({ language, disclosure_token: whatsappDisclosure[language].disclosure_token });
    await expect(page.getByText(width < 720 ? words.mobile_title : words.scan_title, { exact: true })).toBeVisible();
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: words.open })).toHaveAttribute("href", url);
    await page.screenshot({ path: info.outputPath(`whatsapp-waiting-${language}-${width}.png`) });
  });
}
