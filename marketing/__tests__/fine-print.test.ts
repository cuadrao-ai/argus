import { readFileSync } from "node:fs";
import { expect, test } from "bun:test";

const FILES = [
  "components/business-stories.module.css",
  "components/owner-stories.module.css",
  "components/business-hero-visual.module.css",
  "components/legal.module.css",
  "components/touchup.module.css",
];

function channel(hex: string, index: number): number {
  const value = Number.parseInt(hex.slice(index, index + 2), 16) / 255;
  return value <= 0.04045 ? value / 12.92 : ((value + 0.055) / 1.055) ** 2.4;
}

function contrast(foreground: string, background: string): number {
  const luminance = (hex: string) => {
    const color = hex.slice(1);
    return [0, 2, 4].reduce((sum, index, place) => sum + channel(color, index) * [0.2126, 0.7152, 0.0722][place], 0);
  };
  const lighter = Math.max(luminance(foreground), luminance(background));
  const darker = Math.min(luminance(foreground), luminance(background));
  return Math.round(((lighter + 0.05) / (darker + 0.05)) * 100) / 100;
}

test("secondary text on the cream background clears 4.5 to 1", () => {
  expect(contrast("#56635e", "#F7F5EE")).toBe(5.76);
  expect(contrast("#56635e", "#fafbf8")).toBe(6.05);
  expect(contrast("#56635e", "#f1f1e6")).toBe(5.53);
});

test("landing and legal fine print stays at 14px in the secondary color", () => {
  for (const file of FILES) {
    const css = readFileSync(new URL(`../${file}`, import.meta.url), "utf8");
    expect(css).not.toMatch(/font-size:\s*1[0-3]px/);
    expect(css.toLowerCase()).not.toContain("#687a72");
    expect(css.toLowerCase()).not.toContain("#526353");
  }
});
