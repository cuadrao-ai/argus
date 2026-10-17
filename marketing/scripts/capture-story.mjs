import { chromium, expect } from "@playwright/test";
import { mkdir, writeFile } from "node:fs/promises";
import { execFileSync } from "node:child_process";
import { fileURLToPath } from "node:url";

const baseURL = process.env.MARKETING_CAPTURE_URL ?? "http://127.0.0.1:4512";
const root = new URL("../../", import.meta.url);
const output = new URL("docs/reports/evidence/cuadrao-marketing-touchup/scroll-story-screens/", root);
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
const captures = [];
try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    const page = await browser.newPage({ viewport, reducedMotion: "no-preference" });
    for (const [route, locale] of [["/", "es"], ["/en", "en"]]) {
      await page.goto(new URL(route, baseURL).href);
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "scroll");
      const tabs = page.getByRole("tab");
      for (let step = 0; step < await tabs.count(); step++) {
        await tabs.nth(step).click();
        await expect(tabs.nth(step)).toHaveAttribute("aria-selected", "true");
        const file = `story-${locale}-${viewport.width}-${step + 1}.png`;
        await page.screenshot({ path: fileURLToPath(new URL(file, output)) });
        captures.push({ route, file, ...viewport, step: step + 1 });
      }
    }
    await page.close();
  }
  const page = await browser.newPage({ viewport: { width: 844, height: 390 }, reducedMotion: "no-preference" });
  await page.goto(baseURL);
  await expect(page.locator("#la-idea")).toHaveAttribute("data-story-mode", "manual");
  await page.getByRole("tab").nth(1).click();
  await page.screenshot({ path: fileURLToPath(new URL("short-screen-manual.png", output)) });
  captures.push({ route: "/", file: "short-screen-manual.png", width: 844, height: 390, mode: "manual" });
  await page.close();
} finally {
  await browser.close();
}
await writeFile(new URL("manifest.json", output), JSON.stringify({
  sourceCommit: execFileSync("git", ["rev-parse", "HEAD"], { cwd: fileURLToPath(root), encoding: "utf8" }).trim(),
  capturedAt: new Date().toISOString(), baseURL,
  browser: "Playwright Chromium headless, isolated contexts",
  captures,
}, null, 2) + "\n");
console.log(fileURLToPath(output));
