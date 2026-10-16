import { describe, expect, test } from "bun:test";
import i18next from "i18next";
import { renderToStaticMarkup } from "react-dom/server";
import { I18nextProvider } from "react-i18next";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { join, relative } from "node:path";
import {
  effectivePaletteLayout,
  paletteRowActionVariant,
} from "../components/sidebar/command-palette/paletteLayout";

import {
  BELOW_DESKTOP_QUERY,
  BELOW_TABLET_QUERY,
  DESKTOP_LAYOUT,
  DESKTOP_MIN_WIDTH_PX,
  TABLET_MIN_WIDTH_PX,
  layoutForWidth,
  layoutsEqual,
} from "../lib/responsive-layout";
import {
  OVERLAY_HISTORY_KEY,
  claimOverlayEntry,
  isProgrammaticPop,
  markProgrammaticPop,
  openOverlayEntries,
  overlayHistoryState,
  recordOverlayEntry,
  resetOverlayEntries,
} from "../components/layout/useOverlayBackDismiss";
import {
  hasOverlayAbove,
  isTopOverlay,
  overlayStackIds,
  registerOverlayLayer,
  unregisterOverlayLayer,
  resetOverlayStack,
} from "../components/layout/overlayStack";

/** Ordering-only layer: no container, no handlers. */
function openLayer(id: string): void {
  registerOverlayLayer({
    id,
    containerRef: { current: null },
    trapFocus: false,
  });
}
const pushOverlay = openLayer;
const popOverlay = unregisterOverlayLayer;
import { sidebarDrawerDragOutcome } from "../components/sidebar/SidebarDrawer";
import ChatShellMenuTrigger from "../components/chat/ChatShellMenuTrigger";
import SidebarHeader from "../components/sidebar/SidebarHeader";
import SidebarShell from "../components/sidebar/SidebarShell";

/** Every source file under a web subdirectory, for whole-class sweeps. */
function sourceFilesUnder(root: string): { path: string; source: string }[] {
  const found: { path: string; source: string }[] = [];
  const walk = (dir: string) => {
    for (const entry of readdirSync(dir)) {
      const full = join(dir, entry);
      if (statSync(full).isDirectory()) {
        walk(full);
        continue;
      }
      if (entry.endsWith(".ts") || entry.endsWith(".tsx")) {
        found.push({
          path: relative(join(import.meta.dir, ".."), full),
          source: readFileSync(full, "utf-8"),
        });
      }
    }
  };
  walk(join(import.meta.dir, "..", root));
  return found;
}

const globalsCss = readFileSync(
  join(import.meta.dir, "../app/globals.css"),
  "utf-8",
);
const chatInterface = readFileSync(
  join(import.meta.dir, "../components/chat/ChatInterface.tsx"),
  "utf-8",
);
const commandPalette = readFileSync(
  join(import.meta.dir, "../components/sidebar/ChatCommandPalette.tsx"),
  "utf-8",
);
const chatSidebar = readFileSync(
  join(import.meta.dir, "../components/sidebar/ChatSidebar.tsx"),
  "utf-8",
);

async function render(node: React.ReactElement): Promise<string> {
  const i18n = i18next.createInstance();
  await i18n.init({ lng: "en", fallbackLng: false });
  return renderToStaticMarkup(
    <I18nextProvider i18n={i18n}>{node}</I18nextProvider>,
  );
}

describe("responsive layout thresholds", () => {
  test("matches the two thresholds the spec sets", () => {
    expect(TABLET_MIN_WIDTH_PX).toBe(720);
    expect(DESKTOP_MIN_WIDTH_PX).toBe(1024);
  });

  test("classifies each DESIGN.md band by width", () => {
    expect(layoutForWidth(390)).toEqual({
      isBelowTablet: true,
      isBelowDesktop: true,
    });
    expect(layoutForWidth(719)).toEqual({
      isBelowTablet: true,
      isBelowDesktop: true,
    });
    expect(layoutForWidth(720)).toEqual({
      isBelowTablet: false,
      isBelowDesktop: true,
    });
    expect(layoutForWidth(1023)).toEqual({
      isBelowTablet: false,
      isBelowDesktop: true,
    });
    expect(layoutForWidth(1024)).toEqual(DESKTOP_LAYOUT);
    expect(layoutForWidth(1920)).toEqual(DESKTOP_LAYOUT);
  });

  test("queries stop just below each stop so the boundary width is desktop-side", () => {
    expect(BELOW_TABLET_QUERY).toBe("(max-width: 719.98px)");
    expect(BELOW_DESKTOP_QUERY).toBe("(max-width: 1023.98px)");
  });

  test("server and first client paint agree on the desktop band", () => {
    expect(DESKTOP_LAYOUT).toEqual({
      isBelowTablet: false,
      isBelowDesktop: false,
    });
    expect(layoutsEqual(DESKTOP_LAYOUT, layoutForWidth(1440))).toBe(true);
    expect(layoutsEqual(DESKTOP_LAYOUT, layoutForWidth(390))).toBe(false);
  });

  test("never sniffs the pointer type to choose a layout", () => {
    expect(commandPalette).not.toContain("pointer: coarse");
    expect(chatInterface).not.toContain("pointer: coarse");
  });
});

describe("system back closes overlays", () => {
  test("still stamps the entry, for anyone reading the stack", () => {
    const state = overlayHistoryState({ existing: 1 }, "sheet-a");
    expect(state.existing).toBe(1);
    expect(state[OVERLAY_HISTORY_KEY]).toBe("sheet-a");
  });

  test("ownership lives in module scope, not in history.state", () => {
    // Next's App Router replaceState drops foreign keys from history.state, so
    // an overlay that trusted the stamp would never pop its own entry and the
    // next system back would leave Argus.
    resetOverlayEntries();
    expect(claimOverlayEntry("sheet-a")).toBe(false);
    recordOverlayEntry("sheet-a");
    expect(openOverlayEntries()).toEqual(["sheet-a"]);
    expect(claimOverlayEntry("sheet-a")).toBe(true);
    expect(claimOverlayEntry("sheet-a")).toBe(false);
    expect(openOverlayEntries()).toEqual([]);
  });

  test("a user back consumes the entry so close does not pop a second time", () => {
    resetOverlayEntries();
    recordOverlayEntry("sheet-a");
    // popstate path claims it...
    expect(claimOverlayEntry("sheet-a")).toBe(true);
    // ...so the unmount path finds nothing left to pop.
    expect(claimOverlayEntry("sheet-a")).toBe(false);
  });

  test("nested overlays each own their own entry", () => {
    resetOverlayEntries();
    recordOverlayEntry("palette-sheet");
    recordOverlayEntry("menu-sheet");
    expect(openOverlayEntries()).toEqual(["palette-sheet", "menu-sheet"]);
    expect(claimOverlayEntry("menu-sheet")).toBe(true);
    expect(openOverlayEntries()).toEqual(["palette-sheet"]);
    expect(claimOverlayEntry("palette-sheet")).toBe(true);
  });

  test("a remount cannot dismiss itself", () => {
    // Mount pushes, cleanup pops, remount pushes again. The echo of the pop
    // finds the id already claimed and is ignored rather than read as a back.
    resetOverlayEntries();
    recordOverlayEntry("sheet-a");
    expect(claimOverlayEntry("sheet-a")).toBe(true); // cleanup pops
    expect(claimOverlayEntry("sheet-a")).toBe(false); // echo, ignored
    recordOverlayEntry("sheet-a"); // remount
    expect(openOverlayEntries()).toEqual(["sheet-a"]);
  });

  test("entry ownership is what decides a dismissal", () => {
    const source = readFileSync(
      join(import.meta.dir, "../components/layout/useOverlayBackDismiss.ts"),
      "utf-8",
    );
    expect(source).toContain("if (!claimOverlayEntry(overlayId)) return;");
  });
});

describe("sidebar drawer", () => {
  test("a rightward drag never dismisses", () => {
    expect(
      sidebarDrawerDragOutcome({ deltaX: 120, panelWidth: 320, velocityX: 1 }),
    ).toBe("settle");
  });

  test("a short slow drag settles back", () => {
    expect(
      sidebarDrawerDragOutcome({ deltaX: -40, panelWidth: 320, velocityX: 0.05 }),
    ).toBe("settle");
  });

  test("a drag past a third of the panel dismisses", () => {
    expect(
      sidebarDrawerDragOutcome({ deltaX: -140, panelWidth: 320, velocityX: 0.1 }),
    ).toBe("dismiss");
  });

  test("a flick dismisses before the travel threshold", () => {
    expect(
      sidebarDrawerDragOutcome({ deltaX: -30, panelWidth: 320, velocityX: 0.9 }),
    ).toBe("dismiss");
  });

  /*
   * The panel allows vertical panning so Recents can scroll, which means the
   * browser can take the gesture away mid-drag and send `pointercancel`. That
   * is not the user letting go, so it decides nothing: a thumb scrolling the
   * list drifts sideways, and both readings of a real dismissal were reachable
   * from that drift alone.
   */
  test("a cancelled gesture never dismisses, however far or fast it went", () => {
    for (const [deltaX, velocityX] of [
      [-140, 0.1],
      [-30, 0.9],
      [-320, 5],
    ]) {
      expect(
        sidebarDrawerDragOutcome({
          deltaX,
          panelWidth: 320,
          velocityX,
          phase: "cancel",
        }),
      ).toBe("settle");
      // The same numbers on a release, so the case cannot pass by being inert.
      expect(
        sidebarDrawerDragOutcome({
          deltaX,
          panelWidth: 320,
          velocityX,
          phase: "release",
        }),
      ).toBe("dismiss");
    }
  });

  test("cancellation is wired to the cancel phase, not to the release path", () => {
    const source = readFileSync(
      join(import.meta.dir, "../components/sidebar/SidebarDrawer.tsx"),
      "utf8",
    );
    expect(source).toContain("onPointerUp={handleDragEnd}");
    expect(source).toContain("onPointerCancel={handleDragCancel}");
    expect(source).toContain('endGesture(event, "cancel")');
  });

  test("covers 80 to 85 percent so a strip of chat stays tappable", () => {
    const source = readFileSync(
      join(import.meta.dir, "../components/sidebar/SidebarDrawer.tsx"),
      "utf-8",
    );
    expect(source).toContain("w-[82%]");
    expect(source).toContain("bg-black/35");
  });

  test("only wraps the sidebar below the mobile threshold", async () => {
    const rail = await render(
      <SidebarShell
        isBelowTablet={false}
        isDrawerOpen={false}
        onCloseDrawer={() => undefined}
        label="Navigation"
      >
        <p>rail</p>
      </SidebarShell>,
    );
    expect(rail).toBe("<p>rail</p>");

    const closedDrawer = await render(
      <SidebarShell
        isBelowTablet
        isDrawerOpen={false}
        onCloseDrawer={() => undefined}
        label="Navigation"
      >
        <p>drawer</p>
      </SidebarShell>,
    );
    expect(closedDrawer).toBe("");

    const openDrawer = await render(
      <SidebarShell
        isBelowTablet
        isDrawerOpen
        onCloseDrawer={() => undefined}
        label="Navigation"
      >
        <p>drawer</p>
      </SidebarShell>,
    );
    // A viewport overlay is client-only; SSR must not put it inside the shell.
    expect(openDrawer).toBe("");
  });
});

describe("sidebar header", () => {
  test("drawer shows the mark as a static logo and an X as the control", async () => {
    const markup = await render(
      <SidebarHeader
        variant="drawer"
        isOpen
        onToggle={() => undefined}
        onRequestClose={() => undefined}
      />,
    );
    expect(markup).toContain('data-testid="sidebar-drawer-logo"');
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain('data-testid="sidebar-drawer-close"');
    expect(markup).toContain('aria-label="Close sidebar"');
    expect(markup).toContain("h-11 w-11");
  });

  test("the drawer logo is never the dismiss control", async () => {
    const markup = await render(
      <SidebarHeader
        variant="drawer"
        isOpen
        onToggle={() => undefined}
        onRequestClose={() => undefined}
      />,
    );
    const logoIndex = markup.indexOf("sidebar-drawer-logo");
    expect(logoIndex).toBeGreaterThan(-1);
    const before = markup.slice(0, logoIndex);
    const opened = before.split("<button").length - 1;
    const closed = before.split("</button>").length - 1;
    expect(opened).toBe(closed);
  });

  test("web keeps the square-drawer icon it already has", async () => {
    const markup = await render(
      <SidebarHeader variant="rail" isOpen onToggle={() => undefined} />,
    );
    expect(markup).toContain("lucide-panel-left");
    expect(markup).not.toContain("sidebar-drawer-close");
  });
});

describe("mobile top bar", () => {
  test("the trigger is a menu glyph with an accessible name", async () => {
    const markup = await render(
      <ChatShellMenuTrigger onOpen={() => undefined} />,
    );
    expect(markup).toContain('data-testid="chat-shell-menu-trigger"');
    expect(markup).toContain('aria-label="Open sidebar"');
    expect(markup).toContain('aria-haspopup="dialog"');
    // Two bars with the lower one shorter, not an even three-bar hamburger.
    expect(markup).toContain('<line x1="3" y1="9" x2="21" y2="9"></line>');
    expect(markup).toContain('<line x1="3" y1="15" x2="14" y2="15"></line>');
    expect(markup).not.toContain("lucide-menu");
    expect(markup).toContain("h-11 w-11");
  });

  test("activity aggregates onto the trigger", async () => {
    const quiet = await render(
      <ChatShellMenuTrigger onOpen={() => undefined} activityPresentation="none" />,
    );
    expect(quiet).not.toContain("data-conversation-activity");

    const busy = await render(
      <ChatShellMenuTrigger
        onOpen={() => undefined}
        activityPresentation="attention"
      />,
    );
    expect(busy).toContain("data-conversation-activity");
  });

  test("the trigger drops its aggregate once the drawer is open", () => {
    expect(chatInterface).toContain("mobileShell.isDrawerOpen\n                      ? null");
  });

  test("guest keeps Sign up pinned right and loses only the gear", () => {
    expect(chatInterface).toContain("showSettings={!mobileShell.isBelowTablet}");
  });

  test("the drawer carries guest settings at its bottom", () => {
    expect(chatInterface).toContain('placement="drawer"');
    expect(chatSidebar).toContain('data-testid="sidebar-guest-settings"');
  });

  test("the rail preference entry is absent in drawer mode, not greyed", () => {
    expect(chatSidebar).toContain(
      "const sidebarPreferenceHandler = isDrawer ? undefined : onOpenSidebarPreference;",
    );
  });
});

describe("omnisearch below threshold", () => {
  test("is collapsed-only", () => {
    expect(commandPalette).toContain("effectivePaletteLayout(layoutMode, isBelowTablet)");
    expect(effectivePaletteLayout("expanded", true)).toBe("collapsed");
    expect(effectivePaletteLayout("expanded", false)).toBe("expanded");
  });

  test("hides the layout toggle where the band forces collapsed", () => {
    expect(commandPalette).toContain(
      "onToggleLayout={isBelowTablet || !hasPreviewPane ? undefined : toggleLayout}",
    );
  });

  test("a row tap opens the dossier sheet rather than a third pane", () => {
    expect(commandPalette).toContain("setIsDossierSheetOpen(true)");
    expect(commandPalette).toContain(
      '{effectiveLayoutMode === "expanded" && !isBelowDesktop && (',
    );
  });

  test("pins Open conversation inside the sheet", () => {
    const sheet = readFileSync(
      join(
        import.meta.dir,
        "../components/sidebar/command-palette/CommandPaletteDossierSheet.tsx",
      ),
      "utf-8",
    );
    expect(sheet).toContain('data-testid="dossier-sheet-open-conversation"');
    expect(sheet).toContain("titleHidden");
    expect(sheet).toContain("commandPaletteOpenLabelKey(preview)");
    expect(sheet).toContain("min-h-11");
  });

  test("row actions are explicit at every width a touch device is likely to use", () => {
    // Hover reveal cannot be the only affordance where hover does not exist, so
    // the whole band below the desktop stop gets the visible menu.
    expect(commandPalette).toContain("paletteRowActionVariant(isBelowDesktop)");
    expect(paletteRowActionVariant(true)).toBe("menu");
    expect(paletteRowActionVariant(false)).toBe("hover");
  });

  test("row actions read like Recents and announce the object they act on", () => {
    const rowActions = readFileSync(
      join(import.meta.dir, "../components/sidebar/command-palette/rowActionItems.ts"),
      "utf-8",
    );
    const recents = readFileSync(
      join(import.meta.dir, "../components/sidebar/RecentChatActions.tsx"),
      "utf-8",
    );
    // Same visible verbs as the Recents menu, so one surface does not say
    // "Delete" while the other says "Delete conversation".
    for (const key of ["common.rename", "common.archive", "common.delete"]) {
      expect(rowActions).toContain(key);
      expect(recents).toContain(key);
    }
    // The longer form survives as the accessible name, never as visible text.
    expect(rowActions).toContain("accessibleName: t(");
    expect(rowActions).toContain("command_palette.rename_conversation");
  });


  test("pointer, keyboard, and the search field share one row-open path", () => {
    // A keyboard user must not get a different, more destructive navigation.
    expect(commandPalette).toContain("const openRow = useCallback(");
    expect(commandPalette).not.toContain("activateItem(item)");
    expect(commandPalette).not.toContain(
      "activateItem(selectedPreview, action.openAtLeftOff)",
    );
    const rowKeyDown = commandPalette.slice(
      commandPalette.indexOf("const handleRowKeyDown"),
      commandPalette.indexOf("const handleRowKeyDown") + 1200,
    );
    expect(rowKeyDown).toContain("openRow(item, {");
    // The row's own action menu is a control, not part of the row, so Enter
    // there opens the menu rather than the dossier.
    expect(rowKeyDown).toContain('event.target.closest("[data-row-action]")');
  });

  test("Escape ownership is depth, not a list of named children", () => {
    resetOverlayStack();
    pushOverlay("palette");
    expect(hasOverlayAbove("palette")).toBe(false);
    expect(isTopOverlay("palette")).toBe(true);

    pushOverlay("row-menu");
    expect(hasOverlayAbove("palette")).toBe(true);
    expect(isTopOverlay("row-menu")).toBe(true);

    popOverlay("row-menu");
    expect(hasOverlayAbove("palette")).toBe(false);

    // A sheet nests just as a menu does; the parent does not need to know which.
    pushOverlay("dossier-sheet");
    expect(hasOverlayAbove("palette")).toBe(true);
    popOverlay("dossier-sheet");
    popOverlay("palette");
    expect(overlayStackIds()).toEqual([]);
  });

  test("a programmatic pop reaches nobody, however late it lands", () => {
    // A closing overlay spends its entry with back(). That event reaches every
    // listener, including the parent underneath, which by then is topmost and
    // would read it as a real back press: dismissing a language modal closed
    // the drawer behind it.
    resetOverlayEntries();
    markProgrammaticPop();

    // Nothing guarantees popstate arrives inside a frame. Suppression used to
    // expire on one, so a late event went through unsuppressed and the parent
    // closed too, at random. Every listener for the one event must agree.
    const traversal = new Event("popstate");
    expect(isProgrammaticPop(traversal)).toBe(true);
    expect(isProgrammaticPop(traversal)).toBe(true);
    expect(isProgrammaticPop(traversal)).toBe(true);

    // The next event is a real press and must not be swallowed by the same mark.
    expect(isProgrammaticPop(new Event("popstate"))).toBe(false);
  });

  test("two overlays closing together spend one suppression each", () => {
    resetOverlayEntries();
    markProgrammaticPop();
    markProgrammaticPop();

    expect(isProgrammaticPop(new Event("popstate"))).toBe(true);
    expect(isProgrammaticPop(new Event("popstate"))).toBe(true);
    expect(isProgrammaticPop(new Event("popstate"))).toBe(false);
  });

  test("a traversal that never arrives cannot swallow a later real back", () => {
    // back() at the start of session history sends nothing at all, so the mark
    // has to expire on its own or the next real press is eaten forever.
    resetOverlayEntries();
    markProgrammaticPop();
    resetOverlayEntries();
    expect(isProgrammaticPop(new Event("popstate"))).toBe(false);

    const source = readFileSync(
      join(import.meta.dir, "../lib/overlay-history.ts"),
      "utf-8",
    );
    // The safety net is a timeout, not a rendering deadline.
    expect(source).toContain("PROGRAMMATIC_POP_TIMEOUT_MS");
    expect(source).not.toContain("requestAnimationFrame");
  });

  test("a parent cannot answer for the layer above it", () => {
    // Standing down used to be each surface's job, which is why the same bug
    // appeared five times. Input is routed to the topmost layer instead, so a
    // parent is never offered the press in the first place.
    const registry = readFileSync(
      join(import.meta.dir, "../components/layout/overlayStack.ts"),
      "utf-8",
    );
    const back = readFileSync(
      join(import.meta.dir, "../components/layout/useOverlayBackDismiss.ts"),
      "utf-8",
    );
    expect(registry).toContain("const layer = topLayer();");
    expect(registry).toContain("const trap = trappingLayer();");
    // System back still resolves by depth, since popstate reaches everyone.
    expect(back).toContain("if (hasOverlayAbove(overlayId)) return;");
  });

  test("modals the drawer can reach are managed, not exempted", () => {
    // Below 720 the drawer renders ProfileMenu, and these open from there, so
    // dismissing one used to close the drawer underneath it.
    for (const file of [
      "../components/settings/LanguageModal.tsx",
      "../components/settings/UsageModal.tsx",
      "../components/settings/MemoryControlsModal.tsx",
      "../components/settings/AppearanceModal.tsx",
      "../components/settings/ArchivedChatsView.tsx",
      "../components/settings/DeletedItemsView.tsx",
      "../components/sidebar/KeyboardShortcutsOverlay.tsx",
    ]) {
      const source = readFileSync(join(import.meta.dir, file), "utf-8");
      // Managed means it registers, or renders through a shell that does.
      expect(
        /useModalSurface|AdaptivePanel|BottomSheet/.test(source),
      ).toBe(true);
    }
  });

  test("every settings surface the profile menu opens is registered", () => {
    // Enumerated from the dispatch itself rather than from a hand-kept list, so
    // a new entry cannot be added without a layer. Three of these shipped
    // unregistered behind the ones that had already been fixed. The menu is
    // held to owning none of its own, or a panel could re-enter past the
    // dispatch and out of this enumeration's sight.
    const settingsImport = /import (\w+) from "@\/components\/settings\/([\w/]+)"/g;
    const panels = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileSettingsPanels.tsx"),
      "utf-8",
    );
    const menu = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    expect([...menu.matchAll(settingsImport)]).toEqual([]);
    const imported = [...panels.matchAll(settingsImport)];
    expect(imported.length).toBeGreaterThanOrEqual(6);
    // An import that never reaches the registry is a panel nothing can open,
    // and it would pass the managed check below without being dispatchable.
    const registry = panels.slice(panels.indexOf("const SETTINGS_PANELS"));
    expect(
      imported.map((match) => match[1]).filter((name) => !registry.includes(name)),
    ).toEqual([]);
    const hasManagedSurface = (file: string, visited = new Set<string>()): boolean => {
      if (visited.has(file)) return false;
      visited.add(file);
      const source = readFileSync(join(import.meta.dir, file), "utf-8");
      if (/useModalSurface|AdaptivePanel|BottomSheet/.test(source)) return true;
      return [...source.matchAll(/import (\w+) from "@\/components\/([\w/-]+)"/g)]
        .some((match) => new RegExp(`<${match[1]}\\b`).test(source)
          && hasManagedSurface(`../components/${match[2]}.tsx`, visited));
    };
    const unmanaged = imported
      .map((match) => `../components/settings/${match[2]}.tsx`)
      .filter((file) => !hasManagedSurface(file));
    expect(unmanaged).toEqual([]);
  });

  test("a shortcut that opens a surface asks what is already open", () => {
    // Naming the drawer left the same bug behind every other modal: the palette
    // mounted as the new topmost layer at a lower z-index, invisible but
    // holding focus and the keys meant for the dialog on screen.
    const shell = readFileSync(
      join(import.meta.dir, "../components/guest/useGuestShellActions.ts"),
      "utf-8",
    );
    expect(shell).toContain("if (hasOpenOverlay()) {");
    const registry = readFileSync(
      join(import.meta.dir, "../components/layout/overlayStack.ts"),
      "utf-8",
    );
    expect(registry).toContain("export function hasOpenOverlay()");
  });

  test("a surface has one owner, never two", () => {
    // As a sheet the shell owns the layer, the entry and the trap. Registering
    // again alongside it gave one visible panel two owners, and closing it
    // scheduled two history.back() calls for the same entry.
    const menu = readFileSync(
      join(import.meta.dir, "../components/sidebar/ProfileMenu.tsx"),
      "utf-8",
    );
    expect(menu).toContain("isOpen: isMenuVisible && isDrawerPlacement && !asSheet,");
    expect(menu).toContain("isOpen: isMenuVisible && !isDrawerPlacement && !asSheet,");
  });

  test("back-dismiss callbacks are current before input resumes", () => {
    // A passive effect runs after paint, so a press between commit and flush
    // reached the previous render's guard.
    const back = readFileSync(
      join(import.meta.dir, "../components/layout/useOverlayBackDismiss.ts"),
      "utf-8",
    );
    const at = back.indexOf("dismissRef.current = onDismiss;");
    expect(back.lastIndexOf("useIsomorphicLayoutEffect", at)).toBeGreaterThan(
      back.lastIndexOf("useEffect(() => {", at),
    );
  });

  test("a busy confirmation refuses back before spending its entry", () => {
    const confirm = readFileSync(
      join(import.meta.dir, "../components/ui/ConfirmDialog.tsx"),
      "utf-8",
    );
    expect(confirm).toContain("canDismiss: () => !isBusy,");
  });

  test("a confirmation above the drawer answers Escape alone", () => {
    // The exact case: Delete from a recent row raises ConfirmDialog over the
    // drawer. The drawer registered first, so without the stack its earlier
    // capture listener closed it before the dialog could cancel.
    resetOverlayStack();
    pushOverlay("drawer");
    pushOverlay("confirm");
    expect(hasOverlayAbove("drawer")).toBe(true);
    expect(hasOverlayAbove("confirm")).toBe(false);
    popOverlay("confirm");
    expect(hasOverlayAbove("drawer")).toBe(false);
  });

  test("every modal in the nesting chain registers with the stack", () => {
    for (const file of [
      "../components/ui/BottomSheet.tsx",
      "../components/ui/ConfirmDialog.tsx",
      "../components/sidebar/SidebarDrawer.tsx",
    ]) {
      const source = readFileSync(join(import.meta.dir, file), "utf-8");
      // One call registers the layer and brings Escape routing, focus, and
      // system back together.
      expect(source).toContain("useModalSurface");
      // And none of them listens on its own, which is the property that makes
      // the routing authoritative rather than advisory.
      expect(source).not.toContain('document.addEventListener("keydown"');
    }
  });

  test("re-registering an overlay moves it to the top rather than duplicating", () => {
    resetOverlayStack();
    pushOverlay("a");
    pushOverlay("b");
    pushOverlay("a");
    expect(overlayStackIds()).toEqual(["b", "a"]);
    expect(hasOverlayAbove("b")).toBe(true);
  });

  test("every URL rewrite spends the entries, not every caller", () => {
    // Navigating rewrites the URL onto whatever entry is current, and with an
    // overlay open that is the entry the overlay pushed. Popping it on teardown
    // put the previous conversation back in the address bar while the new one
    // was on screen.
    //
    // This used to be one call at one navigation site, which held only for the
    // path somebody remembered. Both writers of the conversation URL spend the
    // entries now, so every path through them is covered including the ones
    // nobody has written yet.
    const routing = readFileSync(
      join(import.meta.dir, "../lib/chat-conversation-routing.ts"),
      "utf-8",
    );
    const writes = [
      ...routing.matchAll(/window\.history\.replaceState/g),
    ].map((match) => match.index ?? -1);
    expect(writes.length).toBeGreaterThan(0);
    for (const at of writes) {
      const before = routing.slice(0, at);
      expect(before.lastIndexOf("consumeOverlayEntriesForNavigation()")).
        toBeGreaterThan(before.lastIndexOf("export function"));
    }
    // And it lives beside the history state it guards rather than in a
    // component, so the routing layer can reach it without importing upward.
    const registry = readFileSync(
      join(import.meta.dir, "../lib/overlay-history.ts"),
      "utf-8",
    );
    expect(registry).toContain(
      "export function consumeOverlayEntriesForNavigation",
    );
  });

  test("no navigation site carries its own entry bookkeeping", () => {
    // A per-caller call is a rule someone has to remember. The chokepoint
    // means a new navigation path cannot get this wrong by omission.
    const callers = sourceFilesUnder("components").filter(
      (file) =>
        file.source.includes("consumeOverlayEntriesForNavigation") &&
        !file.path.endsWith("useOverlayBackDismiss.ts"),
    );
    expect(callers.map((file) => file.path)).toEqual([]);
  });


  test("Escape dismisses one level, not the whole of Omnisearch", () => {
    // The palette hands its keydown to the registry, which offers it only
    // while the palette is topmost. A sheet or a row menu above it therefore
    // answers first without the palette knowing they exist, which is what the
    // named-child guard and then the depth guard were both trying to do.
    expect(commandPalette).toContain("onKeyDown: onPaletteKeyDown,");
    expect(commandPalette).not.toContain('document.addEventListener("keydown"');
    expect(commandPalette).not.toContain("hasOverlayAbove");
    expect(commandPalette).not.toContain("if (isDossierSheetOpen) return;");
  });

  test("reach is decided by width, not by the pointer", () => {
    /*
     * The cluster used to be forced visible under a coarse-pointer query, whose
     * expanded 44px boxes overlapped by 14px and let the edge of Rename archive
     * or delete. Below the desktop stop the row offers an explicit menu whose
     * trigger and items are already 44px, so nothing needs expanding.
     */
    const rowActions = readFileSync(
      join(
        import.meta.dir,
        "../components/sidebar/command-palette/CommandPaletteRowActions.tsx",
      ),
      "utf-8",
    );
    expect(rowActions).toContain("argus-row-hover-actions");
    expect(rowActions).toContain("h-11 w-11");
    expect(globalsCss).not.toContain("@media (any-pointer: coarse)");
  });

  test("the touch-layout date shares metadata space rather than the menu overlay", () => {
    // The mobile date stays in flow and leaves a deliberate gutter before the
    // 44px action target. Only the desktop hover layout keeps its date absolute.
    expect(commandPalette).toContain('rowActionVariant === "menu" && (');
    expect(commandPalette).toContain(
      "ml-auto me-2 shrink-0 whitespace-nowrap",
    );
    expect(commandPalette).toContain('rowActionVariant !== "menu" && (');
    expect(commandPalette).toContain("max-desktop:min-h-11 max-desktop:pe-12");
  });
});

describe("activity rail and starter pills", () => {
  test("the rail is absent below 720 and present from tablet up", () => {
    const rail = readFileSync(
      join(import.meta.dir, "../components/chat/ConversationActivityRail.tsx"),
      "utf-8",
    );
    // Spec section 6 removes the rail below 720. `md:` is Tailwind's 768, so
    // the named stop is the only one that states the rule the spec wrote.
    expect(rail).toContain("hidden tablet:block");
    expect(globalsCss).toContain("--breakpoint-tablet: 45rem;");
  });

  test("starter pills scroll with a peek on narrow screens", () => {
    const starters = readFileSync(
      join(import.meta.dir, "../components/chat/StarterActions.tsx"),
      "utf-8",
    );
    expect(starters).toContain("argus-starter-peek");
    expect(starters).toContain("overflow-x-auto");
    expect(globalsCss).toContain(".argus-starter-peek");
    expect(starters).not.toContain("dismiss");
  });

  test("pills center while they fit and only then become a carousel", () => {
    const starters = readFileSync(
      join(import.meta.dir, "../components/chat/StarterActions.tsx"),
      "utf-8",
    );
    // `safe center` centers the row but falls back to start on overflow, so the
    // first pill can never end up unreachable off the leading edge.
    expect(starters).toContain("[justify-content:safe_center]");
    // The peek promises more pills, so it is measured rather than assumed.
    expect(starters).toContain("scroller.scrollWidth > scroller.clientWidth");
    expect(starters).toContain("new ResizeObserver(sync)");
    expect(starters).toContain('isOverflowing ? "argus-starter-peek" : ""');
    // Trailing padding inside the scroller would widen scrollWidth and make the
    // overflow measurement depend on its own result.
    expect(starters).not.toContain("pe-6");
  });

  test("pills sit above the composer where a thumb reaches them", () => {
    const surface = readFileSync(
      join(import.meta.dir, "../components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );
    // One instance, placed by flex order: pills before the composer on narrow,
    // after it from tablet up.
    expect(surface.match(/<StarterActions/g)?.length).toBe(1);
    expect(surface).toContain("order-2 w-full max-w-2xl max-tablet:mb-3 tablet:order-3");
    expect(surface).toContain('"order-3 w-full max-w-2xl tablet:order-2"');
    expect(surface).toContain('layout={isBelowTablet ? "scroll" : "wrap"}');
  });

  test("the composer and pills settle on the bottom edge below the threshold", () => {
    const surface = readFileSync(
      join(import.meta.dir, "../components/chat/EmptyChatSurface.tsx"),
      "utf-8",
    );
    // The heading absorbs the free space, which pushes the pair to the bottom.
    expect(surface).toContain("max-tablet:flex-1 max-tablet:justify-center");
    // The home indicator must not sit on top of the composer.
    expect(surface).toContain("pb-[max(1rem,env(safe-area-inset-bottom))]");
    // The tall inset is a min-width variant, never a base value a `sm:` rule
    // could win back between 400 and 719px.
    expect(surface).toContain("tablet:pt-[28vh]");
    expect(surface).not.toContain("sm:pt-[28vh]");
    expect(surface).not.toContain("pt-[24vh]");
  });

  test("suggestion rows never clamp: a reason you cannot read is decoration", () => {
    // The clamp's fade also left ghost slivers of the next line under each
    // row on phones. Identity leads the row, so a wrapped reason is legible.
    expect(globalsCss).not.toContain("line-clamp: 2;");
    expect(globalsCss).not.toContain("line-clamp: 1;");
    const rowComponent = readFileSync(
      join(import.meta.dir, "../components/chat/NextMoveRow.tsx"),
      "utf-8",
    );
    expect(rowComponent).toContain("[overflow-wrap:anywhere]");
  });
});

describe("confirmation card on narrow screens", () => {
  test("keeps all five actions and meets the 44px tap target", () => {
    const card = readFileSync(
      join(import.meta.dir, "../components/chat/StrategyConfirmationCard.tsx"),
      "utf-8",
    );
    expect(card).toContain("min-h-11");
    expect(card).toContain("tablet:min-h-9");
    expect(card).toContain("flex flex-wrap gap-2");
  });
});
