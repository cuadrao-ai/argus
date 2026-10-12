import { describe, expect, test } from "bun:test";
import { readFileSync } from "node:fs";
import { join } from "node:path";

const webRoot = join(import.meta.dir, "..");
const manifest = JSON.parse(
  readFileSync(join(webRoot, "public/manifest.json"), "utf-8"),
);
const layout = readFileSync(join(webRoot, "app/layout.tsx"), "utf-8");

/** PNG dimensions live in the IHDR chunk, bytes 16 through 23. */
function pngSize(relativePath: string): { width: number; height: number } {
  const bytes = readFileSync(join(webRoot, "public", relativePath));
  expect(bytes.subarray(1, 4).toString("ascii")).toBe("PNG");
  return {
    width: bytes.readUInt32BE(16),
    height: bytes.readUInt32BE(20),
  };
}

describe("pwa manifest", () => {
  test("is served at the path layout.tsx already references", () => {
    expect(layout).toContain('manifest: "/manifest.json"');
  });

  test("names the app and keeps short_name under a home-screen icon", () => {
    expect(manifest.name).toBe("Cuadrao");
    expect(manifest.short_name.length).toBeLessThanOrEqual(12);
  });

  test("installs standalone with a minimal-ui fallback", () => {
    expect(manifest.display).toBe("standalone");
    expect(manifest.display_override).toEqual(["standalone", "minimal-ui"]);
  });

  test("carries the Cuadrao paper surface as theme and splash background", () => {
    expect(manifest.theme_color).toBe("#fafbf8");
    expect(manifest.background_color).toBe("#fafbf8");
  });

  test("starts and scopes at the app root", () => {
    expect(manifest.start_url).toBe("/");
    expect(manifest.scope).toBe("/");
  });

  test("ships 192 and 512 icons for any purpose", () => {
    const any = manifest.icons.filter(
      (icon: { purpose?: string }) => icon.purpose === "any",
    );
    expect(any.map((icon: { sizes: string }) => icon.sizes).sort()).toEqual([
      "192x192",
      "512x512",
    ]);
  });

  test("every declared icon exists at its declared size", () => {
    for (const icon of manifest.icons) {
      const [width, height] = icon.sizes.split("x").map(Number);
      expect(pngSize(icon.src)).toEqual({ width, height });
      expect(icon.type).toBe("image/png");
    }
  });

  test("declares no screenshots: none of Cuadrao exist yet, and none of Argus remain", () => {
    expect(manifest.screenshots).toBeUndefined();
  });

  test("carries no em dash in install copy", () => {
    expect(manifest.name).not.toContain("—");
    expect(manifest.short_name).not.toContain("—");
    expect(manifest.description).not.toContain("—");
  });
});

describe("document head", () => {
  test("declares a 180x180 apple-touch-icon, which iOS needs", () => {
    expect(layout).toContain('url: "/icons/apple-touch-icon-180.png"');
    expect(layout).toContain('sizes: "180x180"');
    expect(pngSize("icons/apple-touch-icon-180.png")).toEqual({
      width: 180,
      height: 180,
    });
  });

  test("declares theme-color for light and dark", () => {
    expect(layout).toContain('media: "(prefers-color-scheme: light)"');
    expect(layout).toContain('media: "(prefers-color-scheme: dark)"');
    expect(layout).toContain('color: "#172b26"');
    expect(layout).toContain('color: "#fafbf8"');
  });
});
