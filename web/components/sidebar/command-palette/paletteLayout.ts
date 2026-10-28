import type { WorkspaceSearchGroup } from "@/components/chat/ChatWorkspace";

/**
 * What Omnisearch shows at a given width.
 *
 * Geometry follows width, never pointer type. Pointer capability may choose an
 * affordance inside a layout, but it must not turn a wide touch device into the
 * phone layout or a narrow fine-pointer device into the desktop layout.
 */
export type LayoutMode = "expanded" | "collapsed";
export type RowActionVariant = "menu" | "hover";

/**
 * The Business redesign's window: centered on the content canvas and laid over the top bar, as Slack's search
 * opens over its bar; 680px wide, 1040px while it shows a preview beside the results.
 */
export function adaptiveSearchPlacement(viewport: { width: number; height: number }, canvas: { left: number; width: number } | null, layout: LayoutMode) {
  const gutter = 16;
  const width = Math.min(layout === "expanded" ? 1040 : 680, viewport.width - gutter * 2);
  const center = canvas ? canvas.left + canvas.width / 2 : viewport.width / 2;
  const left = Math.max(gutter, Math.min(viewport.width - gutter - width, center - width / 2));
  const top = 12;
  return { position: "fixed" as const, left, top, width, maxWidth: "none", maxHeight: Math.min(viewport.height * 0.8, viewport.height - top - gutter) };
}

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

/**
 * The highlighted workspace hit and the window's width. An adaptive window (Business redesign) previews the first
 * record that has a preview until the person highlights another, so its preview pane never shows a placeholder,
 * and it is wide only while it shows one; any other window keeps the width it was given.
 */
export function workspaceSearchView(groups: readonly WorkspaceSearchGroup[], selection: string | null, adaptive: boolean, isBelowTablet: boolean, given: LayoutMode) {
  const keyed = groups.flatMap((group) => group.hits.map((hit) => ({ key: `${group.id}:${hit.id}`, hit })));
  const key = selection ?? (adaptive ? keyed.find((item) => item.hit.preview)?.key ?? null : null);
  const hit = keyed.find((item) => item.key === key)?.hit;
  const layout: LayoutMode = adaptive ? (hit?.preview && !isBelowTablet ? "expanded" : "collapsed") : given;
  return { key, hit, layout };
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
