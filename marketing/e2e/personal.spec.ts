import { mockWaitlistWidget } from "./waitlist-fixture";
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
  es: { path: "/personal", button: "Avísame cuando pueda probarla", success: "Revisa tu correo." },
  en: { path: "/en/personal", button: "Let me know when I can try it", success: "You're on the list." },
} as const;

test.beforeEach(async ({ request, context, page }, info) => {
  await resetMock(request);
  await mockWaitlistWidget(page);
  await asNewClient(context, info);
});

for (const locale of ["es"] as const) {
  const copy = COPY[locale];

  test.describe(`personal signup ${locale}`, () => {
    test("registers durably and confirms only after the database accepted the row", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      await page.goto(copy.path);
      await page.locator("#personal-email").fill(address.toUpperCase());
      await page.getByRole("button", { name: copy.button }).click();
      await expect(page.getByRole("heading", { name: copy.success })).toBeFocused();
      const { signups } = await mockState(request);
      expect(signups).toHaveLength(1);
      expect(signups[0]).toMatchObject({ email: address, language: locale });
      await expectNothingStoredInBrowser(page);
    });

    test("a repeat registration looks the same and stores one row", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      for (let attempt = 0; attempt < 2; attempt += 1) {
        await page.goto(copy.path);
        await page.locator("#personal-email").fill(address);
        await page.getByRole("button", { name: copy.button }).click();
        await expect(page.getByRole("heading", { name: copy.success })).toBeVisible();
      }
      expect((await mockState(request)).signups).toHaveLength(1);
    });

    test("an unavailable database keeps the email and never claims success", async ({ page, request }, info) => {
      const address = uniqueAddress(info);
      await page.goto(copy.path);
      await page.locator("#personal-email").fill(address);
      await setMode(request, { supabase: "down" });
      await page.getByRole("button", { name: copy.button }).click();
      await expect(page.locator("#signup-error")).toBeVisible();
      await expect(page.locator("#personal-email")).toHaveValue(address);
      await expect(page.getByRole("heading", { name: copy.success })).toHaveCount(0);
      expect((await mockState(request)).signups).toHaveLength(0);

      await setMode(request, { supabase: "up" });
      await page.getByRole("button", { name: copy.button }).click();
      await expect(page.getByRole("heading", { name: copy.success })).toBeVisible();
      expect((await mockState(request)).signups).toHaveLength(1);
    });

    test("links to the privacy page near the form", async ({ page }) => {
      await page.goto(copy.path);
      await page.locator("#signup-privacy a[href*='priva']").click();
      await expect(page).toHaveURL(locale === "es" ? /\/privacidad$/ : /\/en\/privacy$/);
    });
  });

  test(`personal ${locale} cannot submit natively before hydration`, async ({ browser }, info) => {
    const context = await browser.newContext({ javaScriptEnabled: false });
    await asNewClient(context, info);
    const page = await context.newPage();
    await page.goto(copy.path);
    await expect(page.locator("#personal-email")).toBeDisabled();
    await expect(page.locator('main button[type="submit"]')).toBeDisabled();
    expect(new URL(page.url()).search).toBe("");
    await context.close();
  });
}

test("English signup links to the Spanish form and collects nothing", async ({ page, request }) => {
  await page.goto("/en/personal");
  await expect(page.locator("main form")).toHaveCount(0);
  const link = page.getByRole("link", { name: "Let me know when I can try it", exact: true });
  await expect(link).toHaveAttribute("href", "/personal#early-access");
  await link.click();
  await expect(page).toHaveURL(/\/personal#early-access$/);
  await expect(page.getByRole("textbox", { name: "Correo", exact: true })).toBeVisible();
  expect((await mockState(request)).signups).toHaveLength(0);
});
