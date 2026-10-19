import { expect, test } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const baseline = process.env.CUADRAO_LOADING_BASELINE === "true";
const evidence = process.env.CUADRAO_LOADING_EVIDENCE_DIR;

for (const width of [1280, 390]) {
  test(`loading presentation at ${width}px`, async ({ page }) => {
    test.setTimeout(90_000);
    await page.setViewportSize({ width, height: 900 });
    await page.route("**/*", (route) => ["localhost", "127.0.0.1"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    await page.addInitScript(() => {
      const original = window.setTimeout.bind(window);
      window.setTimeout = ((handler: TimerHandler, delay?: number, ...args: unknown[]) => original(handler, delay === 240 ? 1800 : delay, ...args)) as typeof window.setTimeout;
    });
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/v1/me", async (route) => { await held; await route.fallback(); });
    await page.goto("/dev/business-preview");
    if (baseline) await expect(page.locator('[role="status"]')).toBeVisible();
    else {
      await expect(page.getByTestId("fullscreen-loading")).toBeVisible();
      await expect(page.getByTestId("fullscreen-loading").getByRole("status")).toHaveText("Cargando...");
      await expect(page.getByTestId("fullscreen-loading").getByRole("status")).toHaveAttribute("aria-live", "polite");
    }
    const capture = async (name: string) => {
      if (evidence) await page.screenshot({ path: `${evidence}/${baseline ? "before" : "after"}-${name}-${width}.png`, fullPage: true });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    };
    await capture("initial");
    if (!baseline) {
      await page.emulateMedia({ reducedMotion: "reduce" });
      expect(await page.getByTestId("fullscreen-loading-sheen").evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
      await capture("initial-reduced-motion");
    }
    release();
    await expect(page.getByTestId("inicio-por-revisar")).toBeVisible();
    const monthLoading = page.getByTestId("month-close-loading");
    const cards = page.getByTestId("month-close-cards");
    await expect(monthLoading.or(cards)).toBeVisible();
    await capture("overview");
    await expect(cards).toBeVisible();
    const skeleton = page.getByTestId("business-loading");
    for (const name of ["inbox", "expenses", "updates"]) {
      await page.goto(`/dev/business-preview?view=${name}`);
      await expect(skeleton).toBeVisible();
      await capture(name);
      await expect(skeleton).toHaveCount(0);
    }
    await page.goto("/dev/business-preview?receipt=rcpt-ferreteria");
    await expect(skeleton).toBeVisible();
    let skeletonPreview = "";
    if (!baseline) {
      await expect(skeleton).toHaveAttribute("data-layout", "detail");
      const columns = await skeleton.locator('[aria-hidden="true"] > .grid').evaluate((grid) => getComputedStyle(grid).gridTemplateColumns.split(" ").length);
      expect(columns).toBe(width === 390 ? 1 : 2);
      skeletonPreview = await skeleton.getByTestId("business-skeleton-preview").evaluate((element) => getComputedStyle(element).minHeight);
    }
    await capture("receipt");
    await expect(page.getByTestId("business-record-review")).toBeVisible();
    if (!baseline) {
      const loadedPreview = await page.getByTestId("receipt-original-source").locator('[class*="min-h-[200px]"]').evaluate((element) => getComputedStyle(element).minHeight);
      expect(loadedPreview).toBe(skeletonPreview);
      expect(skeletonPreview).toBe(width === 390 ? "200px" : "280px");
    }
  });
}
