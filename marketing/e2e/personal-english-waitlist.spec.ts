import { expect, test } from "@playwright/test";
import { mockState, resetMock, asNewClient } from "./support";
import { mockWaitlistWidget } from "./waitlist-fixture";

test.beforeEach(async ({ page, request, context }, info) => {
  await resetMock(request);
  await asNewClient(context, info);
  await mockWaitlistWidget(page);
});

test("English answers use the shared form, canonical choices and existing Spanish email", async ({ page, request }, info) => {
  await page.goto("/en/personal");
  await page.getByRole("textbox", { name: "Email", exact: true }).fill("english@example.test");
  const methods = page.getByRole("combobox", { name: "How do you track your expenses today?" });
  await expect(methods.locator("option")).toHaveText(["", "I don't track them", "In a notebook or notes", "In Excel or Google Sheets", "In another app", "Another way"]);
  await methods.selectOption({ label: "In a notebook or notes" });
  const wish = page.getByRole("textbox", { name: "What would you like Cuadrao to help you with?" });
  await wish.fill("Account 1234 5678 9012");
  await expect(page.getByText("Remove account or card numbers before submitting.", { exact: true })).toBeVisible();
  await wish.fill("Keep my expenses in order");
  await expect(page.getByText("Do not include account or card details.", { exact: true })).toBeVisible();
  await expect(page.getByRole("link", { name: "Is it for your business? Contact us", exact: true })).toHaveAttribute("href", "/en/contact");
  await expect(page.locator("#signup-privacy a")).toHaveAttribute("href", "/en/privacy");
  await expect(page.locator('[name="website"]')).toHaveAttribute("tabindex", "-1");
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: info.outputPath("english-waitlist-form.png"), fullPage: true });
  const submission = page.waitForRequest((request) => request.url().endsWith("/api/waitlist/signups") && request.method() === "POST");
  await page.getByRole("button", { name: "Let me know when I can try it", exact: true }).click();
  expect((await submission).postDataJSON()).toEqual({ email: "english@example.test", expenseMethod: "En una libreta o notas", wish: "Keep my expenses in order", website: "", captchaToken: "fixture-token" });
  await expect(page.getByRole("heading", { name: "Check your email.", exact: true })).toBeFocused();
  await expect(page.getByText("We sent a link to english@example.test to confirm your place on the Cuadrao personal app waitlist. It expires in 48 hours. The email is in Spanish.", { exact: true })).toBeVisible();
  const state = await mockState(request);
  expect(state.signups).toHaveLength(1);
  expect(state.emails).toHaveLength(1);
  expect(state.emails[0].text).toContain("Confirma");
  await page.screenshot({ path: info.outputPath("english-waitlist-success.png"), fullPage: true });
});

test("English CAPTCHA uses the real widget contract and clears expired and failed tokens", async ({ page }) => {
  await page.route("https://challenges.cloudflare.com/turnstile/v0/api.js*", (route) => route.fulfill({
    contentType: "application/javascript",
    body: `window.turnstile={render:(container,options)=>{window.widgetOptions=options;container.dataset.language=options.language;container.dataset.action=options.action;return 'fixture';},remove:()=>{}};`,
  }));
  await page.goto("/en/personal");
  await expect(page.locator('[data-language="en"][data-action="personal_waitlist"]')).toHaveCount(1);
  const submit = page.getByRole("button", { name: "Let me know when I can try it", exact: true });
  await expect(submit).toBeDisabled();
  for (const callback of ["expired-callback", "error-callback"]) {
    await page.evaluate(() => (window as unknown as { widgetOptions: { callback: (token: string) => void } }).widgetOptions.callback("fixture-token"));
    await expect(submit).toBeEnabled();
    await page.evaluate((name) => (window as unknown as { widgetOptions: Record<string, () => void> }).widgetOptions[name](), callback);
    await expect(submit).toBeDisabled();
  }
});

test("English honeypot submission keeps the shared no-write behavior", async ({ page, request }) => {
  await page.goto("/en/personal");
  await page.locator("#personal-email").fill("trap@example.test");
  await page.locator('[name="website"]').evaluate((input: HTMLInputElement) => { input.value = "https://spam.example.test"; });
  await page.getByRole("button", { name: "Let me know when I can try it", exact: true }).click();
  await expect(page.getByRole("heading", { name: "Check your email.", exact: true })).toBeVisible();
  const state = await mockState(request);
  expect(state.signups).toHaveLength(0);
  expect(state.emails).toHaveLength(0);
});
