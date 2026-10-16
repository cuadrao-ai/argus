import { expect, test } from "@playwright/test";

for (const [path, background] of [["/", "rgb(23, 43, 38)"], ["/en", "rgb(23, 43, 38)"], ["/personal", "rgb(247, 245, 239)"]]) {
  test(`${path} uses its footer color for the root canvas`, async ({ page }) => {
    await page.goto(path);
    await expect(page.locator("html")).toHaveCSS("background-color", background);
    await expect(page.locator("body")).toHaveCSS("background-color", background);
    const footer = page.locator("footer");
    await footer.scrollIntoViewIfNeeded();
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(page.viewportSize()!.width);
    const bounds = (await footer.boundingBox())!;
    expect(bounds.x).toBe(0);
    expect(bounds.width).toBe(page.viewportSize()!.width);
    await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
    expect(await footer.evaluate((node) => Math.abs(node.getBoundingClientRect().bottom - innerHeight))).toBeLessThanOrEqual(1);
  });
}

for (const path of ["/", "/en"]) {
  test(`${path} renders a loaded light wordmark on the dark footer`, async ({ page, request }) => {
    await page.goto(path);
    const logo = page.locator("footer").getByRole("img", { name: "cuadrao", exact: true });
    await logo.scrollIntoViewIfNeeded();
    await expect.poll(() => logo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBeGreaterThan(0);
    const response = await request.get((await logo.getAttribute("src"))!);
    expect(response.ok()).toBe(true);
    expect(await response.text()).toContain('fill="#fafbf8"');
    await expect(logo).toBeVisible();
    await expect(page.locator("footer")).toHaveCSS("background-color", "rgb(23, 43, 38)");
  });
}
