import { describe, expect, test } from "bun:test";
import {
  profileMenuClass,
  profileSubmenuAnchorClass,
  profileSubmenuClass,
} from "../components/sidebar/profileMenuPlacement";

/**
 * The rail is the surface that already worked, so it is pinned literally.
 *
 * Teaching the menu about the drawer meant touching class strings the desktop
 * rail also renders. These are the exact strings from before that change. A
 * refactor that reflows them is free to; one that alters them is a desktop
 * regression, and the diff of a 200-character Tailwind string is not something
 * review reliably catches.
 */

const RAIL_MENU =
  "fixed bottom-16 z-[60] min-w-[220px] rounded-surface border border-black/10 bg-white py-1.5 dark:border-white/10 dark:bg-[#1f2225] [&>button]:mx-1 [&>button]:my-0.5 [&>button]:w-[calc(100%-0.5rem)] [&>button]:rounded-item [&>div>button]:mx-1 [&>div>button]:my-0.5 [&>div>button]:w-[calc(100%-0.5rem)] [&>div>button]:rounded-item";

const RAIL_SUBMENU_SURFACE =
  "rounded-surface border border-black/10 bg-white py-1 dark:border-white/10 dark:bg-[#1f2225] [&>button]:mx-1 [&>button]:my-0.5 [&>button]:w-[calc(100%-0.5rem)] [&>button]:rounded-item";

describe("rail placement is exactly what it was", () => {
  test("the menu keeps its classes and its offsets", () => {
    expect(profileMenuClass("rail", false)).toEqual({
      className: RAIL_MENU,
      left: "16px",
    });
    expect(profileMenuClass("rail", true).left).toBe("68px");
  });

  test("submenus keep flying out to the right at their own widths", () => {
    expect(profileSubmenuClass("rail", "min-h-[294px] min-w-[304px]")).toBe(
      `absolute bottom-0 left-full ml-1.5 min-h-[294px] min-w-[304px] ${RAIL_SUBMENU_SURFACE}`,
    );
    expect(profileSubmenuClass("rail", "min-w-[248px]")).toBe(
      `absolute bottom-0 left-full ml-1.5 min-w-[248px] ${RAIL_SUBMENU_SURFACE}`,
    );
  });
});

describe("drawer placement", () => {
  test("the menu stays in the drawer's own stacking context", () => {
    const { className, left } = profileMenuClass("drawer", false);
    // Portaled to the body it sat under the drawer and opened invisibly.
    expect(className).toContain("absolute");
    expect(className).not.toContain("fixed");
    // Nothing to offset against: it spans the panel it lives in.
    expect(left).toBeUndefined();
    expect(className).toContain("left-0 right-0");
  });

  test("submenus cover the menu instead of overflowing the screen", () => {
    const drawer = profileSubmenuClass("drawer", "min-w-[304px]");
    expect(drawer).not.toContain("left-full");
    expect(drawer).not.toContain("min-w-[304px]");
    // Sized to the menu, which already fits, so a tall submenu on a short
    // screen cannot push its first actions above the top of the viewport.
    expect(drawer).toContain("inset-0");
    expect(drawer).toContain("overflow-y-auto");
  });

  test("only the rail anchors a submenu to its own row", () => {
    // In the drawer the row must not be the containing block, or the submenu
    // is measured against a 44px row instead of the menu.
    expect(profileSubmenuAnchorClass("rail")).toBe("relative");
    expect(profileSubmenuAnchorClass("drawer")).toBe("");
  });

  test("the drawer menu is bounded and scrollable", () => {
    const { className } = profileMenuClass("drawer", false);
    expect(className).toContain("max-h-[70dvh]");
    expect(className).toContain("overflow-y-auto");
  });

  test("touch targets meet the 44px minimum", () => {
    expect(profileMenuClass("drawer", false).className).toContain(
      "[&_button]:min-h-[44px]",
    );
    const submenu = profileSubmenuClass("drawer", "min-w-[248px]");
    expect(submenu).toContain("[&_button]:min-h-[44px]");
    expect(submenu).toContain("[&_a]:min-h-[44px]");
  });

  test("the rail keeps the compact rows it has room for", () => {
    expect(profileMenuClass("rail", false).className).not.toContain(
      "min-h-[44px]",
    );
  });
});
