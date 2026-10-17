import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const baseURL = process.env.MARKETING_CAPTURE_URL ?? 'http://127.0.0.1:4512';
const root = new URL('../../', import.meta.url);
const output = new URL('docs/reports/evidence/cuadrao-marketing-touchup/personal-footer-wordmark/screens/', root);
await mkdir(output, { recursive: true });
const browser = await chromium.launch();
const captures = [];
const errors = [];
try {
  for (const viewport of [{ width: 1440, height: 900 }, { width: 390, height: 844 }]) {
    for (const [route, locale] of [['/personal', 'es'], ['/en/personal', 'en']]) {
      const context = await browser.newContext({ viewport });
      const page = await context.newPage();
      page.on('pageerror', error => errors.push(error.message));
      await page.goto(new URL(route, baseURL).href);
      await expect(page.locator('#personal-email')).toBeEnabled();
      await page.evaluate(() => document.fonts.ready);
      await expect(page.locator('footer img:not([src$=".svg"])')).toHaveCount(0);
      await expect(page.locator('[data-footer-peek]')).toHaveCount(0);
      await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
      await page.waitForTimeout(800);
      const file = `footer-${locale}-${viewport.width}-rest.png`;
      await page.screenshot({ path: fileURLToPath(new URL(file, output)) });
      captures.push({ file, route, ...viewport, state: 'rest' });
      await context.close();
    }
  }
  const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
  await page.goto(new URL('/', baseURL).href);
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight));
  await page.waitForTimeout(1000);
  await page.screenshot({ path: fileURLToPath(new URL('business-footer-unchanged.png', output)) });
  captures.push({ file: 'business-footer-unchanged.png', route: '/', width: 1440, height: 900, state: 'rest' });
} finally { await browser.close(); }
if (errors.length) throw new Error(JSON.stringify(errors));
await writeFile(new URL('manifest.json', output), JSON.stringify({ sourceCommit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: fileURLToPath(root), encoding: 'utf8' }).trim(), capturedAt: new Date().toISOString(), baseURL, browser: 'Playwright Chromium desktop and narrow viewport; static page ending', forms: 'No submissions or provider requests', captures }, null, 2) + '\n');
console.log(fileURLToPath(output));
