import { expect, test } from "@playwright/test";
import { installBreakpointFixture } from "./support/breakpoint-fixture";

const before = process.env.CUADRAO_LOADING_BASELINE === "true";
const evidence = process.env.CUADRAO_LOADING_EVIDENCE_DIR;

for (const width of [1280, 390]) {
  for (const theme of ["light", "dark"] as const) {
    test(`full-screen loading at ${width}px in ${theme}`, async ({ page }) => {
      await page.setViewportSize({ width, height: 900 });
      await page.route("**/*", (route) => ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
      await installBreakpointFixture(page, { language: "es-419", theme, emptyChat: true });
      let release = () => {};
      const held = new Promise<void>((resolve) => { release = resolve; });
      await page.route("**/api/v1/me", async (route) => { await held; await route.fallback(); });
      await page.goto("/dev/business-preview");
      const indicator = page.getByTestId(before ? "conversation-retrieval-state" : "fullscreen-loading");
      await expect(indicator).toBeVisible();
      if (!before) {
        await expect(indicator.getByRole("status")).toHaveText("Cargando");
        const status = indicator.getByRole("status");
        expect(await status.evaluate((node) => getComputedStyle(node).clipPath !== "none" || getComputedStyle(node).clip !== "auto")).toBe(true);
        const geometry = await indicator.evaluate((node) => {
          const logo = Array.from(node.querySelectorAll("img")).find((image) => getComputedStyle(image).display !== "none")!;
          const track = node.querySelector('[data-testid="fullscreen-loading-track"]')!;
          const a = logo.getBoundingClientRect();
          const b = track.getBoundingClientRect();
          return { logo: a.width, bar: b.width, offset: Math.abs(a.x - b.x), center: Math.abs(a.x + a.width / 2 - innerWidth / 2), text: (node as HTMLElement).innerText.trim() };
        });
        expect(geometry).toEqual({ logo: 240, bar: 240, offset: 0, center: 0, text: "Cargando" });
        const sheen = page.getByTestId("fullscreen-loading-sheen");
        expect(await sheen.evaluate((node) => getComputedStyle(node).animationName)).not.toBe("none");
        const positions = await sheen.evaluate(async (node) => {
          const first = getComputedStyle(node).transform;
          await new Promise((resolve) => setTimeout(resolve, 200));
          return [first, getComputedStyle(node).transform];
        });
        expect(positions[0]).not.toBe(positions[1]);
      }
      if (evidence) await page.screenshot({ path: `${evidence}/${before ? "before" : "after"}-${theme}-${width}.png` });
      if (!before) {
        await page.emulateMedia({ reducedMotion: "reduce" });
        expect(await page.getByTestId("fullscreen-loading-sheen").evaluate((node) => getComputedStyle(node).animationName)).toBe("none");
        if (evidence) await page.screenshot({ path: `${evidence}/after-reduced-${theme}-${width}.png` });
      }
      release();
      await expect(indicator).toHaveCount(0);
      await expect(page.getByTestId("overview-real-expenses")).toBeVisible();
    });
  }
}

for (const fast of [true, false]) {
  test(`${fast ? "fast" : "slow"} full-page load uses a 300ms visibility delay`, async ({ page }) => {
    test.skip(before, "The baseline has a different delay.");
    await page.route("**/*", (route) => ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
    await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
    let release = () => {};
    const held = new Promise<void>((resolve) => { release = resolve; });
    await page.route("**/api/v1/me", async (route) => { await held; await route.fallback(); });
    const now = new Date();
    await page.clock.install({ time: now });
    await page.clock.pauseAt(now);
    const requested = page.waitForRequest("**/api/v1/me");
    await page.goto("/dev/business-preview");
    await requested;
    const indicator = page.getByTestId("fullscreen-loading");
    await page.clock.runFor(299);
    await expect(indicator).toHaveCount(0);
    if (fast) {
      const response = page.waitForResponse("**/api/v1/me");
      release();
      await response;
      await page.clock.runFor(1000);
      await expect(indicator).toHaveCount(0);
    } else {
      await page.clock.runFor(1);
      await expect(indicator).toBeVisible();
      const response = page.waitForResponse("**/api/v1/me");
      release();
      await response;
      await expect(indicator).toHaveCount(0);
    }
  });
}

test("the landing session check uses the same full-page bar", async ({ page }) => {
  test.skip(before, "The baseline landing uses a spinner.");
  await page.route("**/*", (route) => ["127.0.0.1", "localhost"].includes(new URL(route.request().url()).hostname) ? route.continue() : route.abort());
  await installBreakpointFixture(page, { language: "es-419", theme: "light", emptyChat: true });
  let release = () => {};
  const held = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/me", async (route) => { await held; await route.fallback(); });
  await page.goto("/");
  await expect(page.getByTestId("fullscreen-loading").getByRole("status")).toHaveText("Cargando");
  release();
  await expect(page.getByTestId("fullscreen-loading")).toHaveCount(0);
});
