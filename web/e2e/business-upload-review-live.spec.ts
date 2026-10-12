import { expect, test, type Page } from "@playwright/test";

// Against the live Business app with mock auth and a local in-memory API: one
// image upload with AI consent must land on the review panel, never on the
// app-level error page, whatever the read found.

const PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg==",
  "base64",
);

async function openBusiness(page: Page) {
  await page.route("**/*", (route) => {
    const { hostname } = new URL(route.request().url());
    return ["127.0.0.1", "localhost"].includes(hostname) ? route.continue() : route.abort("blockedbyclient");
  });
  await page.addInitScript(() => {
    window.localStorage.setItem("argus:sidebar_mode", "expanded");
    window.localStorage.setItem("i18nextLng", "en");
  });
  await page.goto("/biz");
}

test.describe("Upload with consent lands on review", () => {
  // Needs the live app against a local in-memory API with the receipt stub (see the PR
  // body for the launcher); the fixture-only e2e job has no API and skips it.
  test.skip(!process.env.CUADRAO_E2E_LIVE_API, "set CUADRAO_E2E_LIVE_API=1 with a local API behind the web");
  test.use({ viewport: { width: 1280, height: 800 } });

  test("one PNG with AI consent reaches the review panel without a client crash", async ({ page }) => {
    // Only page errors are collected, and they are what the test asserts on.
    const errors: string[] = [];
    page.on("pageerror", (error) => errors.push(`pageerror: ${error.message}\n${error.stack ?? ""}`));
    const detailFetches: string[] = [];
    page.on("request", (request) => {
      if (/\/business\/receipts\/[0-9a-f-]{36}$/.test(request.url()) && request.method() === "GET") detailFetches.push(request.url());
    });

    await openBusiness(page);
    await page.getByTestId("business-create").click();
    await page.getByRole("menuitem", { name: "Upload receipt" }).click();
    const dialog = page.getByRole("dialog", { name: "Upload receipt" });
    await page.locator('input[type="file"]').first().setInputFiles({ name: "image.png", mimeType: "image/png", buffer: PNG });
    await expect(dialog).toContainText("image.png");
    await dialog.getByRole("checkbox").check();
    await dialog.getByRole("button", { name: /Save/ }).click();
    const review = dialog.getByRole("button", { name: "Review saved receipts" });
    await expect(review).toBeVisible({ timeout: 15000 });
    await review.click();

    // The outcome is one of two states; wait for either, then judge.
    await expect(page.getByRole("heading", { name: "Review receipt", exact: true }).or(page.getByText(/couldn't load/))).toBeVisible({ timeout: 15000 });
    test.info().annotations.push({ type: "errors", description: errors.join("\n---\n") || "none" });
    test.info().annotations.push({ type: "detail-fetches", description: String(detailFetches.length) });
    expect(await page.locator("body").innerText()).not.toContain("couldn't load");
    // Dev mode runs effects twice; a stable data source means no further refetch of the record.
    expect(detailFetches.length).toBeLessThanOrEqual(2);
    await expect(page.getByRole("heading", { name: "Review receipt", exact: true })).toBeVisible();
    expect(errors).toEqual([]);
  });
});
