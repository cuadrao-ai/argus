// Captures the durable evidence for the marketing package from a running
// production build. Usage, from marketing/ after `bun run build`:
//   bunx next start -p 4511 &            (no provider variables needed)
//   node ../docs/reports/evidence/cuadrao-marketing-launch/capture.mjs http://127.0.0.1:4511 <commit>
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

// Run from marketing/, whose node_modules holds Playwright.
const { chromium, webkit } = await import(
  pathToFileURL(join(process.cwd(), "node_modules/@playwright/test/index.mjs")).href
);

const [origin = "http://127.0.0.1:4511", commit = "unknown"] = process.argv.slice(2);
const out = dirname(fileURLToPath(import.meta.url));
mkdirSync(join(out, "screens"), { recursive: true });

const PAGES = [
  ["es-home", "/"], ["es-personal", "/personal"], ["es-contact", "/contacto"], ["es-privacy", "/privacidad"],
  ["en-home", "/en"], ["en-personal", "/en/personal"], ["en-contact", "/en/contact"], ["en-privacy", "/en/privacy"],
];
const VIEWPORTS = [["1440", 1440, 900], ["390", 390, 844]];
const report = { commit, origin, capturedAt: new Date().toISOString(), pages: [], redirects: [], icons: [] };

const chromiumBrowser = await chromium.launch();
for (const [width, w, h] of VIEWPORTS) {
  const context = await chromiumBrowser.newContext({ viewport: { width: w, height: h }, reducedMotion: "reduce" });
  for (const [name, path] of PAGES) {
    const page = await context.newPage();
    await page.goto(origin + path, { waitUntil: "networkidle" });
    await page.evaluate(() => document.fonts.ready);
    await page.screenshot({ path: join(out, "screens", `${name}-${width}.jpg`), fullPage: true, type: "jpeg", quality: 62 });
    if (width === "1440") {
      report.pages.push(await page.evaluate((entry) => ({
        path: entry,
        htmlLang: document.documentElement.lang,
        title: document.title,
        canonical: document.querySelector('link[rel="canonical"]')?.href ?? null,
        alternates: [...document.querySelectorAll('link[rel="alternate"][hreflang]')].map((l) => [l.getAttribute("hreflang"), l.getAttribute("href")]),
        icons: [...document.querySelectorAll('link[rel~="icon"], link[rel="apple-touch-icon"]')].map((l) => l.getAttribute("href")),
        ogImage: document.querySelector('meta[property="og:image"]')?.content ?? null,
        cookies: document.cookie,
        localStorageKeys: Object.keys(localStorage).length,
        sessionStorageKeys: Object.keys(sessionStorage).length,
      }), path));
    }
    await page.close();
  }
  await context.close();
}
await chromiumBrowser.close();

// The same pages in WebKit, Safari's engine, where the original icon report came from.
const webkitBrowser = await webkit.launch();
const wkContext = await webkitBrowser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: "reduce" });
for (const [name, path] of [PAGES[0], PAGES[1], PAGES[6]]) {
  const page = await wkContext.newPage();
  await page.goto(origin + path, { waitUntil: "networkidle" });
  await page.evaluate(() => document.fonts.ready);
  await page.screenshot({ path: join(out, "screens", `webkit-${name}-390.jpg`), fullPage: true, type: "jpeg", quality: 62 });
  await page.close();
}
await webkitBrowser.close();

for (const path of ["/business", "/business/personal", "/business/demo", "/business/en", "/business/en/personal", "/business/en/demo", "/es", "/es/contacto"]) {
  const response = await fetch(origin + path, { redirect: "manual" });
  report.redirects.push({ from: path, status: response.status, to: response.headers.get("location") });
}
for (const path of ["/icon.svg", "/favicon.ico", "/apple-icon.png", "/manifest.json"]) {
  const response = await fetch(origin + path);
  report.icons.push({ path, status: response.status, contentType: response.headers.get("content-type"), bytes: (await response.arrayBuffer()).byteLength });
}
const health = await fetch(`${origin}/api/health`);
report.health = { status: health.status, body: await health.json() };
const robots = await fetch(`${origin}/robots.txt`);
report.robots = { text: await robots.text(), xRobotsTag: (await fetch(origin + "/")).headers.get("x-robots-tag") };

writeFileSync(join(out, "browser.json"), JSON.stringify(report, null, 2) + "\n");
console.log(`captured ${PAGES.length * 2 + 3} screenshots and browser.json at ${commit}`);
