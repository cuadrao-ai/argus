import { expect, test, type Page } from "@playwright/test";
import { BUSINESS_PRIVACY_NOTICE_STORAGE_KEY } from "../lib/browser-storage";
import { BUSINESS_PRIVACY_NOTICE_VERSION, MOCK_AUTH_CONSENT_USER_ID } from "../lib/business-privacy-notice";

// Requires a local API with ReceiptStub and no paid provider calls.
// Reading-on review also requires the canonical Business database and Actions.
// Saved owner reading permission governs the real modal upload request.

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function openBusiness(page: Page) {
  await page.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(hostname) ? route.continue() : route.abort("blockedbyclient");
  });
  await page.addInitScript(({ key, userId, version }) => {
    window.localStorage.setItem("argus:sidebar_mode", "expanded");
    window.localStorage.setItem("i18nextLng", "en");
    const record = {
      userId,
      acceptedAt: "2026-10-18T12:00:00.000Z",
      noticeVersion: version,
      locale: "en",
      textSha256: "a".repeat(64),
    };
    window.sessionStorage.setItem(key, JSON.stringify({ [userId]: record }));
  }, { key: BUSINESS_PRIVACY_NOTICE_STORAGE_KEY, userId: MOCK_AUTH_CONSENT_USER_ID, version: BUSINESS_PRIVACY_NOTICE_VERSION });
  await page.goto("/biz");
}

test.describe("Owner upload reaches its saved receipt", () => {
  // Reading-on review requires canonical local Business database and Actions
  // services with ReceiptStub. The memory API supports the saved-unread case only.
  test.skip(!process.env.CUADRAO_E2E_LIVE_API, "set CUADRAO_E2E_LIVE_API=1 with a local API behind the web");
  test.use({ viewport: { width: 1280, height: 800 } });

  test("one PNG with saved owner reading permission reaches review without a client crash", async ({ page }) => {
    // Page errors and console errors are both collected, and both must be empty.
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    page.on("console", (message) => {
      if (message.type() === "error") errors.push(`console: ${message.text()}`);
    });
    const detailFetches: string[] = [];
    page.on("request", (request) => {
      if (/\/business\/receipts\/[0-9a-f-]{36}$/.test(request.url()) && request.method() === "GET") detailFetches.push(request.url());
    });

    await openBusiness(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Upload receipt" }).click();
    const dialog = page.getByRole("dialog", { name: "Upload receipts", exact: true });
    await page.locator('input[type="file"]').first().setInputFiles({ name: "image.png", mimeType: "image/png", buffer: PNG });
    await expect(dialog).toContainText("image.png");
    await expect(dialog.getByRole("checkbox")).toHaveCount(0);
    const turnOn = dialog.getByRole("button", { name: "Turn receipt reading on", exact: true });
    await expect(turnOn.or(dialog.getByRole("button", { name: "Turn reading off", exact: true }))).toBeVisible();
    if (await turnOn.isVisible()) await turnOn.click();
    await expect(dialog.getByTestId("receipt-reading-control")).toContainText("Receipt reading is on.");
    const uploaded = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith("/business/receipts") && response.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save remaining files", exact: true }).click();
    const response = await uploaded;
    expect(response.status()).toBe(200);
    expect(response.request().headers()["x-extraction-consent"]).toBeUndefined();
    const review = dialog.getByRole("button", { name: "Review saved receipts" });
    await expect(review).toBeVisible({ timeout: 15000 });
    await review.click();

    const reviewEntry = page.getByTestId("business-record-review");
    await expect(reviewEntry).toBeVisible({ timeout: 15000 });
    test.info().annotations.push({ type: "errors", description: errors.join("\n---\n") || "none" });
    test.info().annotations.push({ type: "detail-fetches", description: String(detailFetches.length) });
    expect(await page.locator("body").innerText()).not.toContain("couldn't load");
    // Dev mode runs effects twice; a stable data source means no further refetch of the record.
    expect(detailFetches.length).toBeLessThanOrEqual(2);
    await expect(reviewEntry).toContainText("image.png");
    expect(errors).toEqual([]);
  });

  test("reading off saves the original unread and reopens its source after reload", async ({ page }) => {
    const pageErrors: string[] = [];
    page.on("pageerror", (error) => pageErrors.push(error.message));
    await openBusiness(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Upload receipt", exact: true }).click();
    const dialog = page.getByRole("dialog", { name: "Upload receipts", exact: true });
    const turnOff = dialog.getByRole("button", { name: "Turn reading off", exact: true });
    await expect(turnOff.or(dialog.getByRole("button", { name: "Turn receipt reading on", exact: true }))).toBeVisible();
    if (await turnOff.isVisible()) await turnOff.click();
    await expect(dialog.getByTestId("receipt-reading-control")).toContainText("Your receipts are saved unread.");
    const content = Buffer.from("Receipt\nMerchant: Synthetic shop\nTotal: DOP 850.00\n");
    await dialog.locator('input[type="file"]').first().setInputFiles({ name: "unread.txt", mimeType: "text/plain", buffer: content });
    const uploaded = page.waitForResponse((response) =>
      new URL(response.url()).pathname.endsWith("/business/receipts") && response.request().method() === "POST",
    );
    await dialog.getByRole("button", { name: "Save remaining files", exact: true }).click();
    const response = await uploaded;
    expect(response.status()).toBe(200);
    expect(response.request().headers()["x-extraction-consent"]).toBeUndefined();
    const saved = await response.json();
    expect(saved.status).toBe("saved");
    expect(saved.expense_id).toBeNull();
    const detailUrl = `${response.url()}/${saved.id}`;
    const source = await page.request.get(`${detailUrl}/source`);
    expect(source.status()).toBe(200);
    expect(await source.body()).toEqual(content);
    await dialog.getByRole("button", { name: "Review saved receipts", exact: true }).click();
    await expect(page.getByRole("figure", { name: /unread.txt/ })).toBeVisible();
    await expect(page.getByText("Saved, unread.", { exact: true })).toBeVisible();
    await page.reload();
    await expect(page.getByRole("figure", { name: /unread.txt/ })).toBeVisible();
    await expect(page.getByText("Saved, unread.", { exact: true })).toBeVisible();
    await expect(page.getByTestId("receipt-reading-control")).toContainText("Your receipts are saved unread.");
    const detail = await page.request.get(detailUrl);
    expect(detail.status()).toBe(200);
    const reopened = await detail.json();
    expect(reopened.id).toBe(saved.id);
    expect(reopened.status).toBe("saved");
    expect(reopened.expense_id).toBeNull();
    expect(pageErrors).toEqual([]);
  });

});
