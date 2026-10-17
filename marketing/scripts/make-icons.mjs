import { readFileSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { chromium } from "@playwright/test";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const mark = readFileSync(join(root, "brand/cuadrao-mark-light.svg"), "utf8");
const artwork = mark.replace(/<svg[^>]*>/, "").replace(/<\/svg>\s*$/, "");
const svg = `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64"><rect width="64" height="64" rx="14" fill="#fafbf8"/><g transform="translate(32 32) scale(.92) translate(-32 -32)">${artwork}</g></svg>\n`;
writeFileSync(join(root, "app/icon.svg"), svg);

const browser = await chromium.launch();
const page = await browser.newPage();

async function render(size, source = svg) {
  await page.setViewportSize({ width: size, height: size });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${source}`,
  );
  return page.screenshot({ omitBackground: true, clip: { x: 0, y: 0, width: size, height: size } });
}

// iOS fills transparent corners with black and rounds the icon itself, so the
// home-screen icon is a full-bleed square.
writeFileSync(
  join(root, "app/apple-icon.png"),
  await render(180, svg.replace('rx="14"', 'rx="0"')),
);

// An ICO may embed PNG images, so one 48px PNG covers the /favicon.ico request.
const png = await render(48);
const header = Buffer.alloc(22);
header.writeUInt16LE(0, 0);
header.writeUInt16LE(1, 2);
header.writeUInt16LE(1, 4);
header.writeUInt8(48, 6);
header.writeUInt8(48, 7);
header.writeUInt16LE(1, 10);
header.writeUInt16LE(32, 12);
header.writeUInt32LE(png.length, 14);
header.writeUInt32LE(22, 18);
writeFileSync(join(root, "app/favicon.ico"), Buffer.concat([header, png]));

await browser.close();
