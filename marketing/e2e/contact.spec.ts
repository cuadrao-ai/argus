import { expect, test } from "@playwright/test";
import {
  asNewClient,
  expectNothingStoredInBrowser,
  mockState,
  resetMock,
  setMode,
  uniqueAddress,
} from "./support";

const COPY = {
  es: { path: "/contacto", send: "Enviar mensaje", sent: "Recibimos tu mensaje.", unavailable: /No pudimos enviar tu mensaje/ },
  en: { path: "/en/contact", send: "Send message", sent: "We received your message.", unavailable: /We couldn.t send your message/ },
} as const;

test.beforeEach(async ({ request, context }, info) => {
  await resetMock(request);
  await asNewClient(context, info);
});

for (const locale of ["es", "en"] as const) {
  const copy = COPY[locale];

  test.describe(`contact form ${locale}`, () => {
    test("sends one message that reaches the configured inbox with the visitor as reply-to", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      await page.goto(copy.path);
      await page.locator("#contact-name").fill("Marisol Peña");
      await page.locator("#contact-email").fill(address);
      await page.locator("#contact-description").fill("Llevo las cuentas de una ferretería.");
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByRole("heading", { name: copy.sent })).toBeFocused();

      const { emails } = await mockState(request);
      expect(emails).toHaveLength(1);
      expect(emails[0].to).toEqual(["inbox@example.test"]);
      expect(emails[0].reply_to).toBe(address);
      expect(emails[0].text).toContain("Marisol Peña");
      expect(emails[0].text).toContain("ferretería");
      await expectNothingStoredInBrowser(page);
    });

    test("a double click sends one request and one message", async ({ page, request }, info) => {
      let posts = 0;
      page.on("request", (req) => {
        if (req.method() === "POST" && req.url().endsWith("/api/inquiries")) posts += 1;
      });
      await page.goto(copy.path);
      await page.locator("#contact-name").fill("Ana");
      await page.locator("#contact-email").fill(uniqueAddress(info));
      await setMode(request, { resendDelayMs: 600 });
      const button = page.getByRole("button", { name: copy.send });
      await button.dblclick();
      await expect(page.getByRole("heading", { name: copy.sent })).toBeVisible();
      expect(posts).toBe(1);
      expect((await mockState(request)).emails).toHaveLength(1);
    });

    test("an unavailable service keeps the text, and a retry sends exactly one message", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      await page.goto(copy.path);
      await page.locator("#contact-name").fill("Ana");
      await page.locator("#contact-email").fill(address);
      await page.locator("#contact-description").fill("Texto que no debe perderse");
      await setMode(request, { resend: "down" });
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.locator("#contact-failure")).toContainText(copy.unavailable);
      await expect(page.locator("#contact-description")).toHaveValue("Texto que no debe perderse");
      await expect(page.getByRole("heading", { name: copy.sent })).toHaveCount(0);
      expect((await mockState(request)).emails).toHaveLength(0);

      await setMode(request, { resend: "up" });
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByRole("heading", { name: copy.sent })).toBeVisible();
      expect((await mockState(request)).emails).toHaveLength(1);
    });

    test("a retry after a lost response does not send twice", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      await page.goto(copy.path);
      await page.locator("#contact-name").fill("Ana");
      await page.locator("#contact-email").fill(address);
      // The provider accepts the message but the visitor's browser never hears back.
      await page.route("**/api/inquiries", async (route, req) => {
        await route.fetch();
        await route.abort("failed");
        await page.unroute("**/api/inquiries");
        expect(req.method()).toBe("POST");
      });
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.locator("#contact-failure")).toContainText(copy.unavailable);
      expect((await mockState(request)).emails).toHaveLength(1);

      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.getByRole("heading", { name: copy.sent })).toBeVisible();
      const { emails } = await mockState(request);
      expect(emails).toHaveLength(1);
    });

    test("required fields are reported and nothing is sent", async ({ page, request }) => {
      await page.goto(copy.path);
      await page.getByRole("button", { name: copy.send }).click();
      await expect(page.locator("#contact-name-error")).toBeVisible();
      await expect(page.locator("#contact-email-error")).toBeVisible();
      await expect(page.locator("#contact-name")).toBeFocused();
      expect((await mockState(request)).emails).toHaveLength(0);
    });

    test("links to the privacy page next to the form", async ({ page }) => {
      await page.goto(copy.path);
      await page.locator("#contact-privacy a").click();
      await expect(page).toHaveURL(locale === "es" ? /\/privacidad$/ : /\/en\/privacy$/);
    });
  });
}

test("without JavaScript the form cannot be submitted natively", async ({ browser }, info) => {
  const context = await browser.newContext({ javaScriptEnabled: false });
  await asNewClient(context, info);
  const page = await context.newPage();
  await page.goto("/contacto");
  await expect(page.locator("#contact-email")).toBeDisabled();
  await expect(page.locator('main button[type="submit"]')).toBeDisabled();
  await expect(page.locator("main")).toContainText("JavaScript", { useInnerText: true });
  expect(new URL(page.url()).search).toBe("");
  await context.close();
});
