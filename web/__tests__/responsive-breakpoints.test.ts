import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

const globalsCss = readFileSync(
  join(import.meta.dir, "../app/globals.css"),
  "utf-8",
);

function declaredBreakpoints(): Record<string, string> {
  const entries: Record<string, string> = {};
  for (const line of globalsCss.split("\n")) {
    const trimmed = line.trim();
    if (!trimmed.startsWith("--breakpoint-")) continue;
    const [name, value] = trimmed.replace(/;$/, "").split(":");
    entries[name.trim()] = value.trim();
  }
  return entries;
}

// DESIGN.md section 8: Mobile Small <400, Mobile 400-720, Tablet 720-1024,
// Desktop 1024-1280, Large 1280-1920. Values in rem at a 16px root.
const DESIGN_SCALE = {
  "--breakpoint-mobile": "25rem",
  "--breakpoint-tablet": "45rem",
  "--breakpoint-desktop": "64rem",
  "--breakpoint-large": "80rem",
  "--breakpoint-xlarge": "120rem",
} as const;

// Tailwind's own widths, not the DESIGN.md stops. Clearing the defaults means
// these have to be redeclared, and redeclaring them at different widths would
// silently move every `sm:` and `md:` class already in the codebase.
const LEGACY_ALIASES = {
  "--breakpoint-sm": "40rem",
  "--breakpoint-md": "48rem",
  "--breakpoint-lg": "64rem",
  "--breakpoint-xl": "80rem",
  "--breakpoint-2xl": "96rem",
} as const;

describe("responsive breakpoints", () => {
  test("clears the Tailwind default scale before declaring its own", () => {
    expect(globalsCss).toContain("--breakpoint-*: initial;");
  });

  test("declares the DESIGN.md section 8 scale", () => {
    const declared = declaredBreakpoints();
    for (const [name, value] of Object.entries(DESIGN_SCALE)) {
      expect(declared[name]).toBe(value);
    }
  });

  test("names the two thresholds the mobile spec sets", () => {
    const declared = declaredBreakpoints();
    expect(declared["--breakpoint-tablet"]).toBe("45rem");
    expect(declared["--breakpoint-desktop"]).toBe("64rem");
  });

  test("redeclares the Tailwind default names at their own widths", () => {
    const declared = declaredBreakpoints();
    for (const [name, value] of Object.entries(LEGACY_ALIASES)) {
      expect(declared[name]).toBe(value);
    }
  });

  test("declares no breakpoint outside the DESIGN.md stops", () => {
    const allowed = new Set<string>([
      "--breakpoint-*",
      ...Object.keys(DESIGN_SCALE),
      ...Object.keys(LEGACY_ALIASES),
    ]);
    for (const name of Object.keys(declaredBreakpoints())) {
      expect(allowed.has(name)).toBe(true);
    }
  });

  test("keeps the desktop and large stops at their pre-migration widths", () => {
    // lg and xl were already 64rem and 80rem, so desktop markup cannot shift.
    const declared = declaredBreakpoints();
    expect(declared["--breakpoint-lg"]).toBe("64rem");
    expect(declared["--breakpoint-xl"]).toBe("80rem");
  });
});

const POINTER_AFFORDANCE_PATHS = [
  "components/sidebar/pointerAffordances.module.css",
  "components/business-app/transacciones/transacciones-cells.module.css",
] as const;
const pointerInventory = (paths: readonly string[]) => [...paths].sort();

describe("pointer capability stays an affordance concern", () => {
  test("pointer inventory keeps the exact allowed paths regardless of directory order", () => {
    expect(pointerInventory([...POINTER_AFFORDANCE_PATHS].reverse())).toEqual(pointerInventory(POINTER_AFFORDANCE_PATHS));
    expect(pointerInventory([...POINTER_AFFORDANCE_PATHS, "components/global-pointer.css"])).not.toEqual(pointerInventory(POINTER_AFFORDANCE_PATHS));
  });

  test("only the cleared sidebar and record-cell affordances branch on the pointer", () => {
    /*
     * Geometry follows the DESIGN.md widths. Pointer capability answers only
     * whether a hover-revealed control is reachable, so it stays in one CSS
     * module and never becomes a runtime layout branch.
     */
    const offenders: string[] = [];
    const scan = (dir: string) => {
      for (const entry of readdirSync(dir)) {
        const full = join(dir, entry);
        if (statSync(full).isDirectory()) {
          scan(full);
          continue;
        }
        if (!/\.(ts|tsx|css)$/.test(entry)) continue;
        const source = readFileSync(full, "utf-8")
          .replace(/\/\*[\s\S]*?\*\//g, "")
          .replace(/^\s*\/\/.*$/gm, "");
        if (
          /@media[^{]*(?:any-)?pointer\s*:|@media[^{]*hover\s*:|matchMedia\([^)]*(?:pointer|hover)/.test(
            source,
          )
        ) {
          offenders.push(relative(join(import.meta.dir, ".."), full));
        }
      }
    };
    scan(join(import.meta.dir, "..", "components"));
    scan(join(import.meta.dir, "..", "app"));
    expect(pointerInventory(offenders)).toEqual(pointerInventory(POINTER_AFFORDANCE_PATHS));


    const recordCells = readFileSync(join(import.meta.dir, "../components/business-app/transacciones/transacciones-cells.module.css"), "utf-8");
    const approved = [
      "@media (hover:hover) and (pointer:fine) { .emptyActionDash { visibility:visible; } .emptyActionIcon { visibility:hidden; } :global(tr[data-record-key]:hover) .emptyActionDash, :global(tr[data-record-key]:focus-within) .emptyActionDash { visibility:hidden; } :global(tr[data-record-key]:hover) .emptyActionIcon, :global(tr[data-record-key]:focus-within) .emptyActionIcon { visibility:visible; } }",
      "@media (any-pointer:coarse) { .emptyActionDash { visibility:hidden; } .emptyActionIcon { visibility:visible; } }",
    ];
    const mediaBlocks = (source: string) => source.match(/@media[^{}]*\{(?:[^{}]|\{[^{}]*\})*\}/g)?.map((block) => block.replace(/\s+/g, " ").trim()) ?? [];
    expect(mediaBlocks(recordCells)).toEqual(approved);
    expect(mediaBlocks(recordCells + "\n@media (pointer:fine) { :global(body) { display:none; } }")).not.toEqual(approved);
    expect(mediaBlocks(recordCells.replace("visibility:visible", "display:none"))).not.toEqual(approved);

    const affordances = readFileSync(
      join(
        import.meta.dir,
        "../components/sidebar/pointerAffordances.module.css",
      ),
      "utf-8",
    );
    expect(affordances).toContain("(hover: hover) and (pointer: fine)");
    expect(affordances).toContain("(any-pointer: coarse)");
    expect(affordances).not.toMatch(/(?:min|max)-width/);
  });
});
