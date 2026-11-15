import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");

function viewBox(svg) {
  const [, , width, height] = svg.match(/viewBox="([^"]+)"/)[1].split(/\s+/).map(Number);
  return { width, height };
}

// brand/README.md, "Lockup": the lockup's viewBox height is the mark height, 1 em,
// and the clear space is 0.5 em on every side. The email header is always #172b26,
// the one background the dark lockup is drawn for.
function lockup(emPx) {
  const svg = readFileSync(join(root, "brand/cuadrao-lockup-dark.svg"), "utf8");
  const box = viewBox(svg);
  const clear = 0.5 * emPx;
  const artWidth = (box.width / box.height) * emPx;
  return { svg, width: Math.ceil(artWidth + 2 * clear), height: emPx + 2 * clear, art: { left: clear, top: clear, width: artWidth, height: emPx }, density: 2 };
}

// Auth templates published before the lockup header, and mail already delivered,
// load these two names into a 168 x 36 slot. The slot is narrower than the wordmark
// at 36 px tall, so the wordmark is fitted to the width.
function publishedWordmark() {
  const svg = readFileSync(join(root, "brand/cuadrao-wordmark-dark.svg"), "utf8");
  const box = viewBox(svg);
  const slot = { width: 168, height: 36 };
  const side = 2;
  const artWidth = slot.width - 2 * side;
  const artHeight = (box.height / box.width) * artWidth;
  return { svg, ...slot, art: { left: side, top: (slot.height - artHeight) / 2, width: artWidth, height: artHeight }, density: 3 };
}

const images = {
  "lockup-dark.png": lockup(36),
  "wordmark-light.png": publishedWordmark(),
  "wordmark-dark.png": publishedWordmark(),
};

const browser = await chromium.launch();
for (const [file, { svg, width, height, art, density }] of Object.entries(images)) {
  const page = await browser.newPage({ viewport: { width, height }, deviceScaleFactor: density });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}svg{position:absolute;left:${art.left}px;top:${art.top}px;width:${art.width}px;height:${art.height}px}</style>${svg}`,
  );
  const png = await page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width, height } });
  await page.close();
  writeFileSync(join(root, "public/email", file), png);
  console.log(`${file}: ${width * density}x${height * density} px, shown at ${width}x${height}, ${png.length} bytes`);
}
await browser.close();
