import { describe, expect, test } from "bun:test";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";

/**
 * One bottom sheet, owned by one component.
 *
 * A hand-rolled panel can look exactly like the primitive while sharing none of
 * its behavior. The chat header menu did: it drew a grab handle with no drag
 * behind it, skipped the focus trap, and never pushed a history entry, so on an
 * installed PWA the Android back button exited Argus instead of closing the
 * menu. Nothing about its appearance gave that away.
 *
 * These rules fail on the vocabulary rather than on the behavior, because the
 * vocabulary is what a reviewer sees and copies.
 */

const WEB_ROOT = join(import.meta.dir, "..");
const SCAN_ROOTS = ["components", "app"];
const PRIMITIVE = "components/ui/BottomSheet.tsx";

/** The drawer is bottom-sheet adjacent but slides on the other axis. */
const DRAWER = "components/sidebar/SidebarDrawer.tsx";

/**
 * Modals that declare `aria-modal` without going through `useModalSurface`.
 *
 * The first version of this list claimed all of these were unrelated
 * pre-existing surfaces. That was wrong: below 720px the drawer renders
 * ProfileMenu, and Language, Usage, and Memory open from there, so dismissing
 * one closed the drawer underneath it. Those are fixed and off the list.
 *
 * `ProfileMenu` came off next, for the same reason it went on: it is what the
 * drawer's Settings entry opens, and it needed system back and a focus trap of
 * its own before that entry worked at all.
 *
 * What remains is genuinely not reachable from a surface this lane changed.
 *
 * Shrink this list; never add to it.
 */
const UNMANAGED_MODAL_DEBT = new Set([
  "components/chat/DiscoverySourcesPanel.tsx",
  "components/sidebar/RecentsQuickPeek.tsx",
]);

function sourceFiles(): string[] {
  const found: string[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (entry.endsWith(".tsx") || entry.endsWith(".ts")) found.push(full);
    }
  };
  for (const root of SCAN_ROOTS) walk(join(WEB_ROOT, root));
  return found;
}

const FILES = sourceFiles().map((path) => ({
  path: relative(WEB_ROOT, path),
  source: readFileSync(path, "utf-8"),
}));

describe("bottom sheet ownership", () => {
  test("the scan actually reaches the components it claims to cover", () => {
    const paths = FILES.map((file) => file.path);
    expect(paths).toContain(PRIMITIVE);
    expect(paths).toContain("components/chat/ChatHeaderMenu.tsx");
    expect(paths.length).toBeGreaterThan(80);
  });

  test("only the primitive draws a grab handle", () => {
    // A handle is a promise that the surface can be dragged. Drawing one
    // without the drag is worse than drawing nothing.
    const offenders = FILES.filter(
      (file) =>
        file.path !== PRIMITIVE &&
        /h-1\.5 w-12 rounded-full|w-12 h-1\.5 rounded-full/.test(file.source),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  test("only the primitive anchors a rounded panel to the bottom edge", () => {
    const offenders = FILES.filter(
      (file) =>
        file.path !== PRIMITIVE &&
        file.path !== DRAWER &&
        /fixed inset-x-0 bottom-0/.test(file.source) &&
        /rounded-t-/.test(file.source),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  test("every sheet-shaped surface inherits dismissal from the primitive", () => {
    // The primitive is the only place that may own this wiring, so a second
    // implementation cannot quietly forget a piece of it.
    const primitive = FILES.find((file) => file.path === PRIMITIVE)!.source;
    // The three obligations now arrive together, so a surface cannot take one
    // and skip another.
    expect(primitive).toContain("useModalSurface");
    const bundle = readFileSync(
      join(WEB_ROOT, "components/layout/useModalSurface.ts"),
      "utf-8",
    );
    expect(bundle).toContain("useOverlayLayer");
    expect(bundle).toContain("useOverlayBackDismiss");
    expect(bundle).toContain("useModalFocusTrap");
    expect(primitive).toContain('role="dialog"');
    expect(primitive).toContain('aria-modal="true"');
    expect(primitive).toContain("useModalSurface");
    expect(primitive).toContain("argus-sheet-scrim");
    expect(primitive).toContain("onPointerDown={handleDragStart}");
  });

  test("every aria-modal surface traps focus through the shared hook", () => {
    // Declaring aria-modal without managing focus leaves the opener focused
    // behind the scrim, which is how the drawer shipped.
    const offenders = FILES.filter(
      (file) =>
        /aria-modal="true"/.test(file.source) &&
        !UNMANAGED_MODAL_DEBT.has(file.path) &&
        !/useModalSurface/.test(file.source),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  test("every aria-modal surface joins the Escape stack", () => {
    // Otherwise one Escape dismisses two levels.
    const offenders = FILES.filter(
      (file) =>
        /aria-modal="true"/.test(file.source) &&
        !UNMANAGED_MODAL_DEBT.has(file.path) &&
        !/useModalSurface/.test(file.source),
    ).map((file) => file.path);
    expect(offenders).toEqual([]);
  });

  test("the debt list stays honest", () => {
    // A file that got fixed must leave the list, or the list stops meaning
    // anything and a later regression slips back in unnoticed.
    const stillUnmanaged = FILES.filter(
      (file) =>
        UNMANAGED_MODAL_DEBT.has(file.path) &&
        !/useModalSurface/.test(file.source),
    ).map((file) => file.path);
    expect([...UNMANAGED_MODAL_DEBT].sort()).toEqual(stillUnmanaged.sort());
  });

  test("no backdrop is a tab stop", () => {
    /*
     * A full-bleed dismiss button is a pointer affordance. Left in the tab
     * order it is the first thing a focus trap hands the user, because it is
     * rendered before the panel, and Enter on it closes the surface they were
     * trying to read. Every modal here has a visible close control and Escape.
     *
     * This shipped three times, in the language modal, the deletion dialog, and
     * Omnisearch, each caught separately and each fixed by pointing a container
     * ref somewhere else. That is discipline rather than a rule, so the rule is
     * here instead: thirteen of these existed and none opted out.
     */
    const offenders: string[] = [];
    for (const file of FILES) {
      // The class list may carry a scrim colour after the inset, and the first
      // version of this rule required the attribute to end right there. Four
      // backdrops sat outside it, including Omnisearch's.
      for (const match of file.source.matchAll(
        /<button\b[\s\S]{0,400}?className="absolute inset-0[^"]*"/g,
      )) {
        if (!match[0].includes("tabIndex={-1}")) {
          offenders.push(file.path);
        }
      }
    }
    expect(offenders).toEqual([]);
  });

  test("the chat header menu goes through the primitive below the threshold", () => {
    const menu = FILES.find(
      (file) => file.path === "components/chat/ChatHeaderMenu.tsx",
    )!.source;
    expect(menu).toContain("<BottomSheet");
    expect(menu).toContain('height="auto"');
    // The panel line, shared with every other panel.
    expect(menu).toContain("isBelowDesktop");
    // Its own Escape and outside-tap handling must stand down where the sheet
    // owns them, or the two fight over focus restore.
    expect(menu).toContain("if (isOpen && !isBelowDesktop) {");
  });

  test("a menu-shaped sheet hugs its content instead of taking a detent", () => {
    const primitive = FILES.find((file) => file.path === PRIMITIVE)!.source;
    expect(primitive).toContain('auto: "max-h-[70dvh]"');
    // A four-item menu at the short detent would leave a large dead gap.
    expect(primitive).not.toContain('auto: "h-[40dvh]"');
  });
});

// Full-screen surfaces can be opened from any animated shell or card. The
// wrapper owns DOM placement; a new inline fixed overlay is a regression.
test("every fixed full-screen overlay uses the viewport portal owner", () => {
  const offenders = FILES.filter((file) => /\bfixed inset-0\b/.test(file.source) && !file.source.includes("withViewportPortal(")).map((file) => file.path);
  expect(offenders).toEqual([]);
});
