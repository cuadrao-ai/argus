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

/** Geometry approved at the cleared design checkpoint. New values or selectors need review. */
const APPROVED_GEOMETRY: Record<string, readonly string[]> = {
  "components/business-app/foundation/range-picker.module.css": [
    ".preset | border-radius | 8px",
    ".icon,.today,.load | border-radius | 999px",
    ".day | border-radius | 999px",
    ".start | border-radius | 999px 0 0 999px",
    ".end | border-radius | 0 999px 999px 0",
    ".single | border-radius | 999px",
    ".confirm | border-radius | 999px",
    ".mobile .preset | border-radius | 999px"
  ],
  "components/business-app/foundation/business-notifications.module.css": [
    ".bellDot | border-radius | 50%",
    ".filterTrigger, .filterOption | border-radius | 12px",
    ".filterMenu | border-radius | 16px",
    ".dot | border-radius | 50%",
    ".dismiss | border-radius | 50%",
    ".emptyArt | border-radius | 50%",
    ".emptyTitle:focus-visible | border-radius | 4px"
  ],
  "components/business-app/transacciones/records-filter-preview.module.css": [
    ".trigger | border-radius | 999px",
    ".count | border-radius | 999px",
    ".popover | border-radius | 16px",
    ".group | border-radius | 8px",
    ".choice input | border-radius | 4px",
    ".choice input[type=radio] | border-radius | 50%",
    ".choice input[type=radio]:checked::after | border-radius | 50%",
    ".input | border-radius | 8px",
    ".search | border-radius | 999px",
    ".currency | border-radius | 999px",
    ".clear | border-radius | 999px",
    ".apply | border-radius | 999px",
    ".chip | border-radius | 999px",
    ".iconButton | border-radius | 999px",
    ".day | border-radius | 999px",
    ".columnRow | border-radius | 8px",
    ".grip | border-radius | 999px"
  ],
  "components/business-app/transacciones/records-loading-preview.module.css": [
    ".bar | border-radius | 4px",
    ".sort | border-radius | 999px",
    ".pageSize | border-radius | 999px"
  ],
  "components/business-app/transacciones/records-overview-preview.module.css": [
    ".card | border-radius | 30px",
    ".card | border-radius | 16px"
  ],
  "components/business-app/transacciones/records-results-preview.module.css": [
    ".metric | border-radius | 26px",
    ".breakdown | border-radius | 8px",
    ".currencyGroup | border-radius | 20px",
    ".exclusions summary | border-radius | 50%",
    ".exclusions p | border-radius | 12px",
    ".metric | border-radius | 20px"
  ],
  "components/business-app/transacciones/records-annotations-preview.module.css": [
    ".icon | border-radius | 999px",
    ".dialog | border-radius | 16px",
    ".textarea | border-radius | 8px",
    ".footer > button | border-radius | var(--radius-item)",
    ".image | border-radius | 8px",
    ".fileLink | border-radius | 999px"
  ],
  "components/business-app/transacciones/records-page.module.css": [
    ".pages button | border-radius | 999px",
    ".option | border-radius | 8px",
    ".list | border-radius | 16px",
    ".row:focus-visible | border-radius | 8px",
    ".sortHeading:focus-visible | border-radius | 4px"
  ],
  "components/business-app/transacciones/transacciones-cells.module.css": [
    ".detail:focus-visible | border-radius | 4px",
    ".workflow | border-radius | 999px",
    ".noteButton:focus-visible | border-radius | 4px"
  ]
};
function cssGeometry(source: string): string[] {
  return [...source.matchAll(/([^{}]+)\{([^{}]*)\}/g)].flatMap((block) => [...block[2].matchAll(/(border(?:-[a-z]+)*-radius)\s*:\s*([^;}\n]+)/g)].map((radius) => `${block[1].trim().replace(/\s+/g, " ")} | ${radius[1]} | ${radius[2].trim()}`));
}
function unapprovedGeometry(path: string, source: string): string[] {
  if (path.endsWith(".css")) return cssGeometry(source).filter((entry) => !APPROVED_GEOMETRY[path]?.includes(entry));
  const kept = path === "components/ui/Switch.tsx" ? source.replace(/borderRadius:\s*(?:RAIL_H|KNOB) \/ 2/g, "") : path === "components/ui/BottomSheet.tsx" ? source.replace('fullScreen && snap === "full" ? { borderRadius: 0, paddingTop: "env(safe-area-inset-top)" } : {}', "") : source;
  return /\bborderRadius\b|border(?:-[a-z]+)*-radius\s*:/.test(kept) ? [path] : [];
}

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
    const offenders = STRICT.flatMap((path) => unapprovedGeometry(path, read(path)).map((entry) => `${path}: ${entry}`));
    assert.deepEqual(offenders, []);
  });
});

test("approved geometry rejects a changed value, a new selector and unconditional fullscreen corners", () => {
  assert.deepEqual(unapprovedGeometry("components/business-app/transacciones/records-overview-preview.module.css", ".card { border-radius:30px; }"), []);
  assert.ok(unapprovedGeometry("components/business-app/transacciones/records-overview-preview.module.css", ".card { border-radius:31px; }").length);
  assert.ok(unapprovedGeometry("components/business-app/transacciones/records-overview-preview.module.css", ".new { border-radius:30px; }").length);
  assert.ok(unapprovedGeometry("components/ui/BottomSheet.tsx", "style={{ borderRadius: 0 }}").length);
  assert.ok(unapprovedGeometry("components/ui/Switch.tsx", "style={{ borderRadius: 12 }}").length);
});
