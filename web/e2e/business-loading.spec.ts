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
      await expect(page.getByTestId("fullscreen-loading").getByRole("status")).toHaveText("Cargando");
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
    const skeleton = baseline ? page.locator('[role="status"][aria-label="Cargando..."]') : page.getByTestId("business-loading");
    await expect(skeleton).toBeVisible();
    if (!baseline) {
      await expect(skeleton).toHaveAttribute("data-layout", "overview");
      expect(await skeleton.locator('[aria-hidden="true"]').evaluate((element) => getComputedStyle(element).animationName)).toBe("none");
      const geometry = await skeleton.locator('[aria-hidden="true"] > div').evaluate((grid) => ({
        cards: grid.children.length,
        columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
      }));
      expect(geometry).toEqual({ cards: 3, columns: width === 390 ? 1 : 2 });
    }
    await capture("overview");
    await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
    for (const name of ["inbox", "expenses", "updates"]) {
      await page.goto(`/dev/business-preview?view=${name}`);
      await expect(skeleton).toBeVisible();
      await capture(name);
      await expect(skeleton).toHaveCount(0);
    }
    await page.goto("/dev/business-preview?receipt=rcpt-ferreteria");
    await expect(skeleton).toBeVisible();
    if (!baseline) {
      await expect(skeleton).toHaveAttribute("data-layout", "detail");
      const geometry = await skeleton.locator('[aria-hidden="true"] > .grid').evaluate((grid) => ({
        columns: getComputedStyle(grid).gridTemplateColumns.split(" ").length,
        previewHeight: grid.children[0].getBoundingClientRect().height,
      }));
      expect(geometry).toEqual({ columns: width === 390 ? 1 : 2, previewHeight: width === 390 ? 112 : 320 });
    }
    await capture("receipt");
    await expect(page.getByTestId("business-record-review")).toBeVisible();
  });
}
