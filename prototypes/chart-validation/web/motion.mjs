import { chromium } from '../../../web/node_modules/playwright/index.mjs';
import { mkdir, mkdtemp, rename, rm, readFile, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
const output = new URL('../../../docs/reports/evidence/chart-validation/web/', import.meta.url);
const temporary = await mkdtemp(join(tmpdir(), 'argus-chart-motion-'));
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ headless: true });
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, recordVideo: { dir: temporary, size: { width: 390, height: 844 } } });
  const page = await context.newPage();
  await page.goto('http://127.0.0.1:4179');
  await page.waitForFunction(() => window.chartPrototype?.metrics.renders.length > 0);
  await page.locator('#chart').scrollIntoViewIfNeeded();
  await page.waitForTimeout(350);
  const box = await page.locator('#scrub').boundingBox();
  const coords = await page.evaluate(() => Array.from({ length: window.chartPrototype.state.points }, (_, i) => window.chartPrototype.coordinate(i)));
  const cdp = await context.newCDPSession(page);
  const touch = (type, x, y) => cdp.send('Input.dispatchTouchEvent', { type, touchPoints: type === 'touchEnd' || type === 'touchCancel' ? [] : [{ x, y, radiusX: 1, radiusY: 1 }] });
  const y = box.y + 100;
  await touch('touchStart', box.x + coords[0], y);
  for (const x of coords) { await touch('touchMove', box.x + x, y); await page.waitForTimeout(130); }
  await touch('touchEnd');
  await page.waitForTimeout(450);
  await touch('touchStart', box.x + coords.at(-1), y);
  for (const x of [...coords].reverse()) { await touch('touchMove', box.x + x, y); await page.waitForTimeout(75); }
  await touch('touchCancel');
  await page.waitForTimeout(450);
  await touch('touchStart', box.x + 100, y + 70);
  for (let i = 1; i <= 8; i++) { await touch('touchMove', box.x + 100, y + 70 - i * 20); await page.waitForTimeout(45); }
  await touch('touchEnd');
  await page.waitForTimeout(700);
  const video = page.video();
  await context.close();
  await rename(await video.path(), new URL('chromium-touch-motion.webm', output));
  await writeFile(new URL('motion-metadata.json',output),JSON.stringify({sourceHead:execFileSync('git',['rev-parse','HEAD'],{encoding:'utf8'}).trim(),timestamp:new Date().toISOString(),browser:browser.version(),viewport:'390x844 touch emulation',videoSha256:createHash('sha256').update(await readFile(new URL('chromium-touch-motion.webm',output))).digest('hex'),visualStyleSha256:createHash('sha256').update(await readFile(new URL('../fixtures/visual-style.json',import.meta.url))).digest('hex'),sequence:['horizontal scrub','release retains','reverse scrub','cancel restores','vertical page scroll']},null,2)+'\n');
  console.log('Saved short Chromium emulated touch scrub/release/cancel/vertical-scroll recording.');
} finally {
  await browser.close();
  await rm(temporary, { recursive: true, force: true });
}
