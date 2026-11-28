import { readFileSync } from "node:fs";
import { whatsappDisclosure } from "../__tests__/fixtures/whatsapp-disclosure";
import english from "../public/locales/en/common.json";
import spanish from "../public/locales/es-419/common.json";
import { expect, test, type Page } from "@playwright/test";
import { createFixtureBusinessDataSource } from "../components/business-app/fixture-data";
import { FREEZE_CSS, fulfillAcceptedBusinessConsent, installBreakpointFixture } from "./support/breakpoint-fixture";

async function setup(page: Page, available: boolean, history = false, language: "es-419" | "en" = "es-419", theme: "light" | "dark" = "light") {
  await page.emulateMedia({ reducedMotion: "reduce" });
  const requests: string[] = [];
  const historyRequests: string[] = [];
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.route("**/*", route => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language, theme, emptyChat: true });
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
  for (const theme of ["light", "dark"] as const) test.describe(`linked number in ${theme} at ${width}px`, () => {
    test.use({ hasTouch: width === 390 });
    test(`linked WhatsApp settings and unlink at ${width}px in ${theme}`, async ({ page }, info) => {
      const observed = await setup(page, false, false, "es-419", theme);
      await page.clock.setFixedTime(new Date("2026-11-23T12:00:00Z"));
      let count = 3;
      let linked = true;
      const businesses = [
        { space_id: "ferreteria", name: "Ferretería Los Pinos", tax_id: { type: "rnc", value: "131456782" } },
        { space_id: "colmado", name: "Colmado Doña Fefa", tax_id: { type: "cedula", value: "00112345678" } },
        { space_id: "clinica", name: "Clínica Dental Sonrisa", tax_id: { type: "rnc", value: "130987654" } },
      ];
      await page.route(url => url.pathname.endsWith("/api/v1/whatsapp/link"), route => {
        if (route.request().method() === "DELETE") {
          linked = false;
          return route.fulfill({ status: 204 });
        }
        return route.fulfill({ json: { ...whatsappDisclosure["es-419"], linked, last4: "4821", linked_at: "2026-11-12T12:00:00Z",
          reply_language: "es-419", receiving_businesses: businesses, held_count: count } });
      });
      await page.setViewportSize({ width, height: width === 390 ? 844 : 900 });
      async function openSettings() {
        await page.goto("/biz?view=inbox");
        await page.getByTestId("header-profile-trigger").click();
        await page.getByTestId("profile-menu-settings").click();
        await page.getByRole("button", { name: "WhatsApp", exact: true }).click();
      }
      await openSettings();
      const rows = page.getByRole("list", { name: "Negocios que reciben" }).getByRole("listitem");
      await expect(rows).toHaveCount(3);
      await expect(rows.nth(1)).toContainText("Cédula 001-1234567-8");
      await expect(page.getByRole("region", { name: "Archivos sin negocio" })).toContainText("3");
      await expect(page.getByRole("button", { name: "Desvincular número" })).toBeVisible();
      await expect(page.locator("time").filter({ hasText: "Vinculado el 12 nov" })).toBeVisible();
      const trigger = page.getByRole("button", { name: "Qué pasa con lo que envías" });
      await expect(trigger).toHaveCSS("width", "44px");
      await expect(trigger.locator("svg")).toHaveCSS("width", "24px");
      const held = page.getByRole("region", { name: "Archivos sin negocio" });
      const heading = page.getByRole("heading", { name: "Número que termina en 4821" });
      const card = heading.locator("xpath=ancestor::section[1]");
      const original = (await card.boundingBox())!;
      const originalHeading = await heading.boundingBox();
      const originalTrigger = await trigger.boundingBox();
      const capture = async (state: string) => {
        const clip = await page.getByTestId("settings-window").boundingBox();
        return page.screenshot({ path: info.outputPath(`whatsapp-${state}-${width}-${theme}.png`), style: FREEZE_CSS,
          ...(width === 1440 && clip ? { clip } : {}) });
      };
      await capture("linked-closed");
      if (width === 1440) await trigger.hover();
      else await trigger.tap();
      await expect(page.getByRole("tooltip")).toHaveText(spanish.settings.whatsapp.reading_info);
      const explanation = card.getByRole("tooltip");
      await expect(explanation).toBeVisible();
      const bubble = (await explanation.boundingBox())!;
      const expanded = (await card.boundingBox())!;
      const number = (await heading.boundingBox())!;
      expect(number).toEqual(originalHeading);
      expect(await trigger.boundingBox()).toEqual(originalTrigger);
      const date = (await card.locator("time").boundingBox())!;
      const badge = (await card.locator("svg").first().boundingBox())!;
      expect(expanded.height - original.height).toBeGreaterThanOrEqual(bubble.height);
      expect(bubble.y).toBeGreaterThanOrEqual(number.y + number.height);
      expect(bubble.y + bubble.height).toBeLessThanOrEqual(date.y);
      expect(bubble.x).toBeGreaterThanOrEqual(badge.x + badge.width);
      expect(bubble.x + bubble.width).toBeLessThanOrEqual(expanded.x + expanded.width);
      expect(date.y + date.height).toBeLessThanOrEqual(expanded.y + expanded.height);
      expect(expanded.y + expanded.height).toBeLessThanOrEqual((await held.boundingBox())!.y);
      await capture("linked-open");
      await page.keyboard.press("Escape");
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      expect(await card.boundingBox()).toEqual(original);
      const unlink = page.getByRole("button", { name: "Desvincular número" });
      await trigger.focus();
      await trigger.press("Tab");
      await page.keyboard.press("Shift+Tab");
      await expect(trigger).toBeFocused();
      await expect(page.getByRole("tooltip")).toBeVisible();
      await held.click();
      await expect(page.getByRole("tooltip")).toHaveCount(0);
      await unlink.click();
      const confirm = page.getByRole("alertdialog");
      await expect(confirm.getByRole("button", { name: "Cancelar" })).toBeFocused();
      await expect(confirm.getByRole("listitem")).toHaveCount(4);
      await capture("held-confirm");
      await page.keyboard.press("Escape");
      await expect(unlink).toBeFocused();
      await unlink.click();
      await confirm.getByRole("button", { name: "Desvincular", exact: true }).click();
      await expect(page.getByRole("button", { name: "Vincular mi WhatsApp" })).toBeVisible();
      await expect(held).toContainText("3");
      linked = true;
      count = 0;
      await openSettings();
      await unlink.click();
      await expect(confirm).toContainText(spanish.settings.whatsapp.unlink_empty);
      await expect(confirm.getByRole("listitem")).toHaveCount(0);
      await confirm.screenshot({ path: info.outputPath(`whatsapp-empty-confirm-${width}-${theme}.png`), style: FREEZE_CSS });
      expect(observed.errors).toEqual([]);
    });
  });

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
    await page.clock.install();
    // Local design captures use the disclosures exported by the running backend version.
    const source = process.env.WHATSAPP_CAPTURE_DISCLOSURES;
    const disclosure = source ? JSON.parse(readFileSync(source, "utf8"))[language] as typeof whatsappDisclosure.en : whatsappDisclosure[language];
    let ready = true;
    await page.route((url) => url.pathname.endsWith("/api/v1/whatsapp/link") && url.searchParams.get("language") === language, route => route.fulfill({
      json: { ...disclosure, linked: false, receiving_businesses: ready ? [{ space_id: "elsewhere", name: "Negocio de prueba" }] : [], held_count: 0 },
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
    const capture = (state: string) => page.screenshot({
      path: info.outputPath(`whatsapp-${state}-${language}-${width}.png`), style: FREEZE_CSS,
    });
    const openSettings = async () => {
      await page.goto("/biz?view=inbox");
      await page.getByTestId("header-profile-trigger").click();
      await page.getByTestId("profile-menu-settings").click();
      await page.getByRole("button", { name: "WhatsApp", exact: true }).click();
    };
    await openSettings();
    const link = page.getByRole("button", { name: words.link_phone });
    await expect(link).toBeVisible();
    await expect(page.getByText(disclosure.disclosure, { exact: true })).toBeVisible();
    await capture("ready");
    const issued = page.waitForRequest((request) => new URL(request.url()).pathname.endsWith("/whatsapp/link-codes") && request.method() === "POST");
    await link.click();
    expect((await issued).postDataJSON()).toEqual({ language, disclosure_token: disclosure.disclosure_token });
    await expect(page.getByText(width < 720 ? words.mobile_title : words.scan_title, { exact: true })).toBeVisible();
    await expect(page.getByText(message, { exact: true })).toBeVisible();
    await expect(page.getByRole("link", { name: words.open })).toHaveAttribute("href", url);
    if (width < 720) {
      const description = page.getByText(words.send_steps, { exact: true });
      expect(await description.evaluate(node => getComputedStyle(node.parentElement!).borderTopWidth)).toBe("0px");
      const gap = await description.evaluate(node => {
        const waiting = document.querySelector('[role="timer"]')!;
        return node.getBoundingClientRect().top - waiting.getBoundingClientRect().bottom;
      });
      expect(gap).toBeGreaterThan(0);
    } else {
      for (const label of [words.scan_camera, words.scan_send, words.scan_return]) {
        await expect(page.getByRole("listitem").filter({ hasText: label })).toHaveCSS("font-size", "14px");
      }
    }
    await capture("waiting");
    await page.clock.fastForward(11 * 60 * 1000);
    await expect(page.getByText(words.expired_title, { exact: true })).toBeVisible();
    await expect(page.getByRole("button", { name: words.new_code })).toBeVisible();
    await capture("expired");

    ready = false;
    await openSettings();
    await expect(page.getByText(words.setup_title, { exact: true })).toBeVisible();
    await expect(link).toHaveCount(0);
    await capture("setup");
  });
}
