import assert from "node:assert/strict";
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { describe, test } from "bun:test";

const ROOT = join(import.meta.dir, "..");

function sources(dir: string): string[] {
  return readdirSync(join(ROOT, dir), { withFileTypes: true }).flatMap((entry) => {
    const path = join(dir, entry.name);
    if (entry.isDirectory()) return sources(path);
    return /\.(tsx?|css)$/.test(entry.name) ? [path] : [];
  });
}

const read = (path: string) => readFileSync(join(ROOT, path), "utf8");

/** Every corner class, with any variant prefix, side and `!`. Group 1 is the size. */
const CORNER = /(?<![\w-])!?rounded(?:-(?:t|b|l|r|s|e|tl|tr|bl|br|ss|se|es|ee))?-(\[[^\]]*\]|[a-z0-9]+)(?![\w-])/g;
const SCALE = new Set(["mark", "item", "surface", "full", "none"]);

function offScale(path: string): string[] {
  return [...read(path).matchAll(CORNER)].filter((match) => !SCALE.has(match[1])).map((match) => match[0]);
}

/** Business-owned files: every corner is on the scale. */
const STRICT = [...sources("components/business-app"), ...sources("components/ui"), "components/sidebar/command-palette/WorkspaceSearchResults.tsx"];

/**
 * Shared files whose Business branches are on the scale while their personal
 * branches are out of this design's reach. Their off-scale count may only fall.
 */
const PERSONAL_BRANCHES: Record<string, number> = {
  "components/sidebar/SidebarNavButton.tsx": 1,
  "components/sidebar/SidebarHeader.tsx": 1,
  "components/sidebar/ChatCommandPalette.tsx": 4,
  "components/sidebar/ChatSidebar.tsx": 5,
  "components/sidebar/profileMenuPlacement.ts": 0,
  "components/sidebar/ProfileMenu.tsx": 0,
};

/** Inline radii that are not ad hoc, each with why. */
const INLINE_RADIUS_ALLOWED: Record<string, string> = {
  "components/ui/Switch.tsx": "a pill computed from the rail and knob geometry, so the curves stay concentric",
};

describe("Business corners come from one scale", () => {
  test("the scale is defined once, as Tailwind theme tokens: 4, 8 and 16", () => {
    const css = read("app/globals.css");
    assert.deepEqual(
      [...css.matchAll(/--radius-(\w+):\s*([^;]+);/g)].map(([, name, value]) => [name, value.trim()]),
      [["mark", "4px"], ["item", "8px"], ["surface", "16px"]],
    );
  });

  test("the guard sees an ad-hoc corner", () => {
    const sample = 'className="rounded-[12px] dark:rounded-lg !rounded-md [&>a]:rounded-t-[20px] rounded-item rounded-l-full"';
    assert.deepEqual(
      [...sample.matchAll(CORNER)].filter((match) => !SCALE.has(match[1])).map((match) => match[0]),
      ["rounded-[12px]", "rounded-lg", "!rounded-md", "rounded-t-[20px]"],
    );
  });

  test("no Business file uses a corner off the scale", () => {
    const offenders = STRICT.flatMap((path) => offScale(path).map((corner) => `${path}: ${corner}`));
    assert.deepEqual(offenders, []);
  });

  test("shared files add no off-scale corner beside their Business branches", () => {
    const grown = Object.entries(PERSONAL_BRANCHES)
      .map(([path, allowed]) => ({ path, allowed, found: offScale(path).length }))
      .filter(({ found, allowed }) => found > allowed);
    assert.deepEqual(grown, []);
  });

  test("no Business file sets an inline or CSS radius outside the allowlist", () => {
    const offenders = STRICT.filter((path) => /\bborderRadius\b|border(?:-[a-z]+)*-radius\s*:/.test(read(path))).filter((path) => !(path in INLINE_RADIUS_ALLOWED));
    assert.deepEqual(offenders, []);
  });
});
