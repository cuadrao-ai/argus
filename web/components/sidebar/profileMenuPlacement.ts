/**
 * Where the profile menu puts itself, and why it depends on what opened it.
 *
 * From the rail it is a detached popover: portaled to the body, pinned near the
 * bottom left, with submenus flying out to the right into open desktop space.
 * None of that survives a drawer. Portaled out, it landed under the drawer's
 * own layer and opened invisibly; flown out to the right, its submenus cleared
 * the right edge of a 390px screen by 155px.
 *
 * So the drawer keeps the menu inside the panel's stacking context and stacks
 * submenus upward at the parent's width instead.
 */

export type ProfileMenuPlacement = "rail" | "drawer" | "header";

/**
 * Inside a sheet a submenu is the sheet's whole body, so it needs no surface of
 * its own: the shell already supplies the panel, the title and the way back.
 */
export const SHEET_SUBMENU_CLASS =
  "[&_button]:min-h-[44px] [&_a]:min-h-[44px]";

const MENU_SURFACE =
  "rounded-[14px] border border-black/10 bg-white py-1.5 dark:border-white/10 dark:bg-[#1f2225] [&>button]:mx-1 [&>button]:my-0.5 [&>button]:w-[calc(100%-0.5rem)] [&>button]:rounded-[10px] [&>div>button]:mx-1 [&>div>button]:my-0.5 [&>div>button]:w-[calc(100%-0.5rem)] [&>div>button]:rounded-[10px]";

const SUBMENU_SURFACE =
  "rounded-[12px] border border-black/10 bg-white py-1 dark:border-white/10 dark:bg-[#1f2225] [&>button]:mx-1 [&>button]:my-0.5 [&>button]:w-[calc(100%-0.5rem)] [&>button]:rounded-[10px]";

/** Touch needs the 44px minimum from DESIGN.md section 17. */
const TOUCH_TARGETS = "[&_button]:min-h-[44px]";

export function profileMenuClass(
  placement: ProfileMenuPlacement,
  sidebarCollapsed: boolean,
): { className: string; left: string | undefined } {
  if (placement === "drawer") {
    return {
      // Bounded so it cannot outgrow the screen, and scrollable so nothing in
      // it becomes unreachable when it does hit the bound.
      className: `absolute bottom-full left-0 right-0 z-30 mb-1.5 max-h-[70dvh] overflow-y-auto overscroll-contain ${TOUCH_TARGETS} ${MENU_SURFACE}`,
      left: undefined,
    };
  }
  if (placement === "header") {
    // Opened from the top-right profile control on desktop workspaces.
    return {
      className: `fixed right-4 top-16 z-[60] min-w-[220px] tablet:right-8 ${MENU_SURFACE}`,
      left: undefined,
    };
  }
  return {
    className: `fixed bottom-16 z-[60] min-w-[220px] ${MENU_SURFACE}`,
    left: sidebarCollapsed ? "68px" : "16px",
  };
}

/**
 * Whether a row establishes the positioning context for its own submenu.
 *
 * On the rail it must: the submenu flies out beside that row. In the drawer it
 * must not. Anchored to the row, a submenu taller than the space above it, such
 * as Data Controls on a short screen with Personalization present, put its top
 * and its first actions off the top of the viewport with no way to scroll to
 * them. Anchored to the menu instead, it covers the menu it came from and can
 * never be taller than a surface that already fits.
 */
export function profileSubmenuAnchorClass(
  placement: ProfileMenuPlacement,
): string {
  return placement === "drawer" ? "" : "relative";
}

export function profileSubmenuClass(
  placement: ProfileMenuPlacement,
  railSizeClass: string,
): string {
  if (placement === "drawer") {
    return `absolute inset-0 overflow-y-auto overscroll-contain ${TOUCH_TARGETS} [&_a]:min-h-[44px] ${SUBMENU_SURFACE}`;
  }
  if (placement === "header") {
    return `absolute right-full top-0 mr-1.5 ${railSizeClass} ${SUBMENU_SURFACE}`;
  }
  return `absolute bottom-0 left-full ml-1.5 ${railSizeClass} ${SUBMENU_SURFACE}`;
}
