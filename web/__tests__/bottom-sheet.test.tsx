import { describe, expect, test } from "bun:test";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { join } from "node:path";

import { BottomSheetSurface as BottomSheet,
  bottomSheetDragOutcome,
  bottomSheetHeightClass,
} from "../components/ui/BottomSheet";
import { nextFocusIndex } from "../components/layout/useModalFocusTrap";

const source = readFileSync(
  join(import.meta.dir, "../components/ui/BottomSheet.tsx"),
  "utf-8",
);
const globalsCss = readFileSync(
  join(import.meta.dir, "../app/globals.css"),
  "utf-8",
);

function renderSheet(
  overrides: Partial<React.ComponentProps<typeof BottomSheet>> = {},
): string {
  return renderToStaticMarkup(
    <BottomSheet
      isOpen
      onClose={() => undefined}
      title="Run dossier"
      closeLabel="Close sheet"
      {...overrides}
    >
      <p>body</p>
    </BottomSheet>,
  );
}

describe("bottom sheet heights", () => {
  test("maps the three spec detents to distinct heights", () => {
    expect(bottomSheetHeightClass("full")).toBe("h-[96dvh]");
    expect(bottomSheetHeightClass("tall")).toBe("h-[70dvh]");
    expect(bottomSheetHeightClass("short")).toBe("h-[40dvh]");
  });

  test("renders the requested height on the panel", () => {
    expect(renderSheet({ height: "full" })).toContain("h-[96dvh]");
    expect(renderSheet({ height: "short" })).toContain("h-[40dvh]");
  });

  test("defaults to the sources detent", () => {
    expect(renderSheet()).toContain("h-[70dvh]");
  });
});

describe("bottom sheet dismissal", () => {
  test("an upward drag never dismisses", () => {
    expect(
      bottomSheetDragOutcome({ deltaY: -200, sheetHeight: 600, velocityY: 2 }),
    ).toBe("settle");
  });

  test("a short slow drag settles back", () => {
    expect(
      bottomSheetDragOutcome({ deltaY: 40, sheetHeight: 600, velocityY: 0.05 }),
    ).toBe("settle");
  });

  test("a drag past a quarter of the sheet dismisses", () => {
    expect(
      bottomSheetDragOutcome({ deltaY: 160, sheetHeight: 600, velocityY: 0.1 }),
    ).toBe("dismiss");
  });

  test("a flick dismisses before the travel threshold", () => {
    expect(
      bottomSheetDragOutcome({ deltaY: 70, sheetHeight: 600, velocityY: 1.2 }),
    ).toBe("dismiss");
  });

  /*
   * The grip sits directly above a scrolling body, so the browser can decide
   * mid-drag that a downward pull was a scroll and take the gesture back. That
   * arrives as `pointercancel`, carrying the travel and direction of a real
   * dismissal, and the sheet closed under the user's thumb.
   */
  test("a cancelled gesture never dismisses, however far or fast it went", () => {
    for (const [deltaY, velocityY] of [
      [160, 0.1],
      [70, 1.2],
      [600, 5],
    ]) {
      expect(
        bottomSheetDragOutcome({
          deltaY,
          sheetHeight: 600,
          velocityY,
          phase: "cancel",
        }),
      ).toBe("settle");
      // The same numbers on a release, so the case cannot pass by being inert.
      expect(
        bottomSheetDragOutcome({
          deltaY,
          sheetHeight: 600,
          velocityY,
          phase: "release",
        }),
      ).toBe("dismiss");
    }
  });

  test("short sheets still need real travel", () => {
    // 25 percent of a 40dvh sheet is under the floor, so the floor governs.
    expect(
      bottomSheetDragOutcome({ deltaY: 50, sheetHeight: 200, velocityY: 0.1 }),
    ).toBe("settle");
    expect(
      bottomSheetDragOutcome({ deltaY: 70, sheetHeight: 200, velocityY: 0.1 }),
    ).toBe("dismiss");
  });

  test("the scrim dismisses and the close control is visible", () => {
    const markup = renderSheet();
    expect(markup).toContain("argus-sheet-scrim");
    expect(markup).toContain('aria-label="Close sheet"');
  });
});

describe("bottom sheet required action", () => {
  test("removes the close control when dismissal is disabled", () => {
    expect(renderSheet({ dismissible: false })).not.toContain('aria-label="Close sheet"');
    expect(renderSheet()).toContain('aria-label="Close sheet"');
  });
});

describe("bottom sheet keyboard handling", () => {
  test("Escape is routed to it by the registry, not listened for", () => {
    // The sheet installs nothing. The registry offers Escape to the topmost
    // layer only, so a menu or confirmation above it answers first without the
    // sheet needing to know that anything is above it.
    expect(source).toContain("onEscape: dismissible ? onClose : () => {},");
    expect(source).not.toContain('document.addEventListener("keydown"');
    expect(source).not.toContain("hasOverlayAbove");
  });

  test("Tab containment belongs to the registry, not to each surface", () => {
    const registry = readFileSync(
      join(import.meta.dir, "../components/layout/overlayStack.ts"),
      "utf-8",
    );
    expect(source).toContain("useModalSurface({");
    // Containment applies to whichever layer is topmost, which is the only
    // place that knows. Per-modal Tab listeners are what let focus escape a
    // dialog nested in the drawer.
    expect(registry).toContain('if (event.key === "Tab")');
    // And a non-trapping top layer hands containment down rather than off, so
    // a menu opened in the drawer cannot let Tab reach the page behind it.
    expect(registry).toContain("const trap = trappingLayer();");
    expect(source).not.toContain("FOCUSABLE_SELECTOR");
  });

  test("focus wraps at both ends so it cannot escape", () => {
    expect(
      nextFocusIndex({ count: 3, currentIndex: 2, direction: "focus-next" }),
    ).toBe(0);
    expect(
      nextFocusIndex({ count: 3, currentIndex: 0, direction: "focus-previous" }),
    ).toBe(2);
    expect(
      nextFocusIndex({ count: 3, currentIndex: 0, direction: "focus-next" }),
    ).toBe(1);
  });

  test("an unfocused sheet enters at the first stop", () => {
    expect(
      nextFocusIndex({ count: 3, currentIndex: -1, direction: "focus-next" }),
    ).toBe(0);
  });

  test("restores focus to the opener on close", () => {
    const trap = readFileSync(
      join(import.meta.dir, "../components/layout/useModalFocusTrap.ts"),
      "utf-8",
    );
    expect(trap).toContain("opener.focus()");
    // And somewhere durable when the opener went away with the drawer.
    expect(trap).toContain("returnFocusRef");
  });
});

describe("bottom sheet accessibility and touch baseline", () => {
  test("is a modal dialog with an accessible name", () => {
    const markup = renderSheet();
    expect(markup).toContain('role="dialog"');
    expect(markup).toContain('aria-modal="true"');
    expect(markup).toContain("aria-labelledby=");
    expect(markup).toContain("Run dossier");
  });

  test("keeps the accessible name when the heading is visually hidden", () => {
    const markup = renderSheet({ titleHidden: true });
    expect(markup).toContain("sr-only");
    expect(markup).toContain("aria-labelledby=");
    expect(markup).toContain("Run dossier");
  });

  test("describes the sheet only when a description is given", () => {
    expect(renderSheet()).not.toContain("aria-describedby=");
    expect(renderSheet({ description: "Sources for this run" })).toContain(
      "aria-describedby=",
    );
  });

  test("the close control meets the 44px tap target", () => {
    expect(renderSheet()).toContain("h-11 w-11");
  });

  test("the close control carries the DESIGN.md focus ring", () => {
    expect(renderSheet()).toContain("focus-visible:ring-[0.125rem]");
  });

  test("form controls inside a sheet cannot drop below 16px", () => {
    expect(globalsCss).toContain(
      ".argus-sheet :is(input, select, textarea)",
    );
    expect(globalsCss).toContain(
      "font-size: max(1rem, var(--argus-sheet-input-font-size, 1rem))",
    );
  });

  test("sits on the bottom edge rather than centered", () => {
    expect(renderSheet()).toContain("items-end");
    expect(renderSheet()).toContain("rounded-t-[28px]");
  });

  test("the scrolling body contains its overscroll", () => {
    expect(renderSheet()).toContain("overscroll-contain");
  });

  test("only the grip claims the drag gesture", () => {
    expect(globalsCss).toContain(".argus-sheet-grip {\n  touch-action: none;");
    expect(source).toContain("argus-sheet-grip");
    expect(source).toContain("onPointerDown={handleDragStart}");
  });

  test("a press on a header control never starts a drag", () => {
    // Capturing the pointer on pointerdown would swallow the close button click.
    expect(source).toContain("event.target.closest(INTERACTIVE_SELECTOR)");
    expect(source).toContain(
      'const INTERACTIVE_SELECTOR = "a[href],button,input,select,textarea,[role=\'button\']"',
    );
  });

  test("the pointer is captured only once a press reads as a drag", () => {
    expect(source).toContain("Math.abs(deltaY) > DRAG_CAPTURE_THRESHOLD_PX");
  });

  test("honors reduced motion", () => {
    const reducedMotionBlocks = globalsCss.split(
      "@media (prefers-reduced-motion: reduce)",
    );
    expect(
      reducedMotionBlocks.some((block) => block.includes(".argus-sheet-enter")),
    ).toBe(true);
  });

  test("renders nothing while closed", () => {
    expect(renderSheet({ isOpen: false })).toBe("");
  });

  test("renders a pinned footer when one is given", () => {
    const markup = renderSheet({ footer: <button>Open conversation</button> });
    expect(markup).toContain("argus-sheet-footer");
    expect(markup).toContain("Open conversation");
  });
});
