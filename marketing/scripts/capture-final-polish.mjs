import { chromium, webkit, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const root = new URL('../../', import.meta.url);
const output = new URL('docs/reports/evidence/cuadrao-marketing-touchup/final-polish/screens/', root);
const baseURL = process.env.MARKETING_CAPTURE_URL ?? 'http://127.0.0.1:4512';
await mkdir(output, { recursive: true });
const captures = [];
const errors = [];
for (const browserType of [chromium, webkit]) {
  const browser = await browserType.launch();
  try {
    for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
      for (const [route, name] of [['/', 'business-es'], ['/en', 'business-en'], ['/personal', 'personal-es'], ['/en/personal', 'personal-en']]) {
        const context = await browser.newContext({ viewport, reducedMotion: 'reduce' });
        const page = await context.newPage();
        page.on('pageerror', error => errors.push(error.message));
        await page.goto(new URL(route, baseURL).href);
        await page.evaluate(() => document.fonts.ready);
        for (const image of await page.locator('img').all()) {
          await image.scrollIntoViewIfNeeded();
          await image.evaluate(async node => { await node.decode(); });
        }
        await expect(page.locator('footer img:not([src$=".svg"]), [data-footer-peek], main img[src*="florist"], main img[src*="accountant"]')).toHaveCount(0);
        expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
        await page.evaluate(() => scrollTo(0, 0));
        const prefix = `${browserType.name()}-${name}-${viewport.width}`;
        await page.screenshot({ path: fileURLToPath(new URL(`${prefix}-page.png`, output)), fullPage: true });
        await page.evaluate(() => scrollTo(0, document.documentElement.scrollHeight));
        const crop = page.locator('footer > div[aria-hidden="true"]');
        await expect.poll(() => crop.evaluate(node => Math.abs(node.getBoundingClientRect().bottom - innerHeight))).toBeLessThanOrEqual(1);
        await page.screenshot({ path: fileURLToPath(new URL(`${prefix}-footer.png`, output)) });
        captures.push({ route, browser: browserType.name(), ...viewport, files: [`${prefix}-page.png`, `${prefix}-footer.png`] });
        await context.close();
      }
    }
  } finally { await browser.close(); }
}
if (errors.length) throw new Error(JSON.stringify(errors));
await writeFile(new URL('manifest.json', output), JSON.stringify({ sourceCommit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: fileURLToPath(root), encoding: 'utf8' }).trim(), capturedAt: new Date().toISOString(), baseURL, forms: 'No submissions; provider-disabled preview', captures }, null, 2) + '\n');
console.log(`${captures.length} Chromium/WebKit ES/EN desktop/mobile views passed; ${captures.length * 2} screenshots.`);
