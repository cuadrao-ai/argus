import { describe, expect, test } from "bun:test";
import { existsSync, readFileSync } from "node:fs";
import { dirname, join, relative, resolve } from "node:path";

/**
 * Anything that can be open while the drawer is has to outrank the drawer.
 *
 * The drawer shipped at z-100 while every surface it hosts sits at 70 to 80,
 * so tapping Settings opened the profile menu underneath the panel that
 * launched it. Nothing looked broken: the menu mounted, its buttons were in the
 * DOM with real bounding boxes, and hit-testing found the drawer on top. Only a
 * human on a phone could see that the tap did nothing.
 *
 * The first version of this test walked only what the drawer imports, and
 * missed Recents Quick Peek because it is a sibling rendered through
 * `KeyboardShortcutSurfaces`. Being a sibling is not protection: its shortcut
 * still fired with the drawer open, so it opened at z-65 behind a z-68 drawer,
 * invisible but focusable. The walk starts from the drawer's host now, which
 * covers anything the same screen can render.
 *
 * Reviews do not catch this, because the two numbers live in different files
 * and neither is wrong on its own.
 */

const WEB_ROOT = join(import.meta.dir, "..");
const DRAWER = "components/sidebar/SidebarDrawer.tsx";
/** The drawer takes its content as children, so the walk has to start there too. */
const DRAWER_CONTENT = "components/sidebar/ChatSidebar.tsx";
/** Renders the drawer and every sibling surface the same screen can show. */
const DRAWER_HOST = "components/chat/ChatInterface.tsx";

/**
 * Surfaces that sit below the drawer and are allowed to, because they cannot be
 * open at the same time. Each one needs a mechanism, asserted below, not a
 * belief. Anything else is a surface that would open invisibly.
 */
const CANNOT_COEXIST_WITH_DRAWER = new Set([
  // Opening search closes the drawer first.
  "components/sidebar/ChatCommandPalette.tsx",
  // Its shortcut is gated on the drawer being closed.
  "components/sidebar/RecentsQuickPeek.tsx",
]);

/** Every full-screen overlay a file declares. */
function overlayLayers(source: string): number[] {
  return [...source.matchAll(/fixed inset-0 z-\[(\d+)\]/g)].map((match) =>
    Number(match[1]),
  );
}

function resolveImport(fromFile: string, specifier: string): string | null {
  const base = specifier.startsWith("@/")
    ? join(WEB_ROOT, specifier.slice(2))
    : specifier.startsWith(".")
      ? resolve(dirname(fromFile), specifier)
      : null;
  if (!base) return null;
  for (const candidate of [
    `${base}.tsx`,
    `${base}.ts`,
    join(base, "index.tsx"),
    join(base, "index.ts"),
  ]) {
    if (existsSync(candidate)) return candidate;
  }
  return null;
}

/** Everything the screen holding the drawer can render, transitively. */
function drawerScreen(): Map<string, string> {
  const found = new Map<string, string>();
  const queue = [DRAWER, DRAWER_CONTENT, DRAWER_HOST].map((path) =>
    join(WEB_ROOT, path),
  );
  while (queue.length > 0) {
    const file = queue.pop()!;
    const key = relative(WEB_ROOT, file);
    if (found.has(key)) continue;
    const source = readFileSync(file, "utf-8");
    found.set(key, source);
    for (const match of source.matchAll(/from\s+"([^"]+)"/g)) {
      const next = resolveImport(file, match[1]);
      if (next) queue.push(next);
    }
  }
  return found;
}

const SCREEN = drawerScreen();
const DRAWER_LAYER = overlayLayers(SCREEN.get(DRAWER)!)[0];

describe("drawer layering", () => {
  test("the walk reaches both what the drawer opens and what sits beside it", () => {
    // A silently narrow graph would make every assertion below vacuous.
    expect(SCREEN.has("components/sidebar/ProfileMenu.tsx")).toBe(true);
    expect(SCREEN.has("components/sidebar/RecentsQuickPeek.tsx")).toBe(true);
    expect(SCREEN.size).toBeGreaterThan(100);
  });

  test("the drawer declares exactly one overlay layer", () => {
    expect(overlayLayers(SCREEN.get(DRAWER)!)).toEqual([DRAWER_LAYER]);
  });

  test("every surface that can share the screen outranks the drawer", () => {
    const buried: string[] = [];
    for (const [path, source] of SCREEN) {
      // The drawer and its own panel are the layer everything else clears.
      if (path === DRAWER || path === DRAWER_CONTENT) continue;
      if (CANNOT_COEXIST_WITH_DRAWER.has(path)) continue;
      for (const layer of overlayLayers(source)) {
        if (layer <= DRAWER_LAYER) buried.push(`${path} z-[${layer}]`);
      }
    }
    expect(buried).toEqual([]);
  });

  test("each exception actually cannot coexist", () => {
    const host = SCREEN.get(DRAWER_HOST)!;
    // Bind the assertion to the opener itself. A bare `closeDrawer()` anywhere
    // in the file passed while a second entry point, the guest shell's own key
    // listener, still opened the palette straight into a hidden layer.
    expect(host).toMatch(/onOpenOmnisearch:[\s\S]{0,240}closeDrawer\(\)/);
    // And the shortcut layer treats an open drawer as a modal, so nothing it
    // owns can open behind it.
    expect(host).toMatch(/modalOpen:[\s\S]{0,200}mobileShell\.isDrawerOpen/);
  });

  test("the exception list stays honest", () => {
    // A surface that got raised above the drawer must leave the list, or the
    // list stops meaning anything.
    const stillBelow = [...CANNOT_COEXIST_WITH_DRAWER].filter((path) =>
      overlayLayers(SCREEN.get(path) ?? "").some(
        (layer) => layer <= DRAWER_LAYER,
      ),
    );
    expect([...CANNOT_COEXIST_WITH_DRAWER].sort()).toEqual(stillBelow.sort());
  });

  test("the drawer still covers the page it sits over", () => {
    // Lowering it to clear the dialogs must not drop it under chat chrome.
    for (const layer of overlayLayers(SCREEN.get(DRAWER_HOST)!)) {
      expect(layer).toBeLessThan(DRAWER_LAYER);
    }
  });
});
