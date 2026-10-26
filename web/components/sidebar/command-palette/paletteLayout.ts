/**
 * What Omnisearch shows at a given width.
 *
 * Geometry follows width, never pointer type. Pointer capability may choose an
 * affordance inside a layout, but it must not turn a wide touch device into the
 * phone layout or a narrow fine-pointer device into the desktop layout.
 */
export type LayoutMode = "expanded" | "collapsed";
export type RowActionVariant = "menu" | "hover";

export function businessSearchPlacement(viewport: { width: number; height: number }, anchor: { right: number; bottom: number } | null, layout: LayoutMode) {
  const gutter = 16;
  const right = Math.max(gutter, Math.min(viewport.width - gutter - 280, viewport.width - (anchor?.right ?? viewport.width - 180)));
  const top = Math.min(anchor ? anchor.bottom + 8 : 72, viewport.height - 160);
  return {
    position: "fixed" as const,
    right,
    top: Math.max(gutter, top),
    width: Math.min(layout === "expanded" ? 1152 : 512, viewport.width - right - gutter),
    maxWidth: "none",
    maxHeight: viewport.height - Math.max(gutter, top) - gutter,
  };
}

/** Below the mobile threshold there is no room for a second pane. */
export function effectivePaletteLayout(
  layoutMode: LayoutMode,
  isBelowTablet: boolean,
): LayoutMode {
  return isBelowTablet ? "collapsed" : layoutMode;
}

/**
 * Every width below the desktop stop gets the explicit 44px menu. At the
 * desktop stop, CSS may reveal compact inline actions for a fine pointer while
 * retaining that touch-safe menu whenever a coarse pointer is available.
 */
export function paletteRowActionVariant(
  isBelowDesktop: boolean,
): RowActionVariant {
  return isBelowDesktop ? "menu" : "hover";
}
