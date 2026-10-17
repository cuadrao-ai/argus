import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const root = join(import.meta.dir, "..");
const tiled = readFileSync(join(root, "app/icon.svg"), "utf8");
const light = readFileSync(join(root, "brand/cuadrao-mark-light.svg"), "utf8");
const paths = (svg: string) => [...svg.matchAll(/<path[^>]* d="([^"]+)"/g)].map((match) => match[1]);

// The light-background mark is the same geometry as the tiled icon without its tile.
describe("light-background mark", () => {
  test("draws the same three shapes as the tiled icon", () => {
    expect(paths(light)).toHaveLength(3);
    expect(paths(light)).toEqual(paths(tiled));
  });

  test("keeps the lean transform and omits the tile", () => {
    expect(light).toContain('transform="translate(6.8 0) skewX(-12)"');
    expect(light).not.toContain("<rect");
  });
});

const brand = (name: string) => readFileSync(join(root, "brand", name), "utf8");
const fills = (svg: string) => [...svg.matchAll(/stop-color="(#[0-9a-f]{6})"/g)].map((match) => match[1]);

describe("dark-background mark", () => {
  test("preserves its shapes and dark-surface palette without the tile", () => {
    const dark = brand("cuadrao-mark-dark.svg");
    expect(paths(dark)).toEqual(paths(tiled));
    expect(fills(dark)).toEqual(["#fffcf2", "#e3dcc2", "#8fa38f", "#5b7566", "#b6e87a", "#7fcb4f"]);
    expect(dark).toContain('transform="translate(6.8 0) skewX(-12)"');
    expect(dark).not.toContain("<rect");
  });
});

describe("lockups", () => {
  test.each([
    ["cuadrao-lockup-light.svg", "cuadrao-mark-light.svg"],
    ["cuadrao-lockup-dark.svg", "cuadrao-mark-dark.svg"],
  ])("%s embeds the shapes of %s", (lockup, mark) => {
    expect(paths(brand(lockup)).slice(0, 3)).toEqual(paths(brand(mark)));
    expect(fills(brand(lockup))).toEqual(fills(brand(mark)));
  });

  test("the wordmark paths are the same letters in both colours", () => {
    const light = paths(brand("cuadrao-wordmark.svg"));
    expect(light).toHaveLength(1);
    expect(paths(brand("cuadrao-wordmark-dark.svg"))).toEqual(light);
    expect(paths(brand("cuadrao-lockup-light.svg")).at(-1)).toEqual(light[0]);
    expect(brand("cuadrao-wordmark.svg")).toContain('fill="#172b26"');
    expect(brand("cuadrao-wordmark-dark.svg")).toContain('fill="#fafbf8"');
  });
});

describe("wordmark specification", () => {
  test("states the styling the website's .wordmark rule uses", () => {
    const css = readFileSync(join(root, "components/business.module.css"), "utf8");
    const rule = css.match(/\n\.wordmark \{([^}]*)\}/)?.[1] ?? "";
    expect(rule).toMatch(/700 35px\/1 var\(--font-space-grotesk\)/);
    expect(rule).toContain("letter-spacing: -0.085em");
    const readme = brand("README.md");
    expect(readme).toContain("weight **700**");
    expect(readme).toContain("**-0.085em**");
  });
});

describe("intrinsic size", () => {
  test.each(["cuadrao-lockup-light.svg", "cuadrao-lockup-dark.svg", "cuadrao-wordmark.svg", "cuadrao-wordmark-dark.svg"])(
    "%s declares a width and height in the aspect of its viewBox",
    (file) => {
      const root = brand(file).match(/<svg[^>]*>/)?.[0] ?? "";
      const width = Number(root.match(/ width="([\d.]+)"/)?.[1]);
      const height = Number(root.match(/ height="([\d.]+)"/)?.[1]);
      const [, , viewWidth, viewHeight] = (root.match(/viewBox="([^"]+)"/)?.[1] ?? "").split(" ").map(Number);
      expect(width).toBeGreaterThan(0);
      expect(height / width).toBeCloseTo(viewHeight / viewWidth, 3);
    },
  );
});

const markGroup = (svg: string) => svg.match(/<g transform="translate\(6\.8 0\) skewX\(-12\)">.*?<\/g>/s)?.[0] ?? "";

describe("whole mark group", () => {
  test("preserves opacity in the dark mark and dark lockup", () => {
    const group = markGroup(brand("cuadrao-mark-dark.svg"));
    expect(group).toContain('opacity=".55"');
    expect(markGroup(brand("cuadrao-lockup-dark.svg"))).toBe(group);
  });

  test("is identical in the light mark, favicon and light lockup", () => {
    expect(markGroup(tiled)).toBe(markGroup(light));
    expect(fills(tiled)).toEqual(fills(light));
    expect(markGroup(brand("cuadrao-lockup-light.svg"))).toBe(markGroup(brand("cuadrao-mark-light.svg")));
  });

  test("the dark lockup carries the same wordmark path in the paper colour", () => {
    const dark = brand("cuadrao-lockup-dark.svg");
    expect(paths(dark).at(-1)).toEqual(paths(brand("cuadrao-wordmark.svg"))[0]);
    expect(dark).toMatch(/<path transform="[^"]*" fill="#fafbf8"/);
    expect(brand("cuadrao-lockup-light.svg")).toMatch(/<path transform="[^"]*" fill="#172b26"/);
  });

  test("the icon tile is the site's paper", () => {
    expect(tiled).toContain('<rect width="64" height="64" rx="14" fill="#fafbf8"/>');
  });
});

