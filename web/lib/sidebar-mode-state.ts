import type { SidebarMode } from "@/components/sidebar/ChatSidebar";

type SidebarNavigationState = {
  currentOpen: boolean;
  mode: SidebarMode;
};

export function sidebarOpenAfterTransientNavigation({
  currentOpen,
  mode,
}: SidebarNavigationState): boolean {
  if (mode === "expanded") {
    return currentOpen;
  }
  return false;
}

export function businessSidebarModes(stored: string | null): Record<string, SidebarMode> {
  if (!stored) return {};
  try {
    const parsed: unknown = JSON.parse(stored);
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    return Object.fromEntries(Object.entries(parsed).filter(([, mode]) => mode === "expanded" || mode === "collapsed" || mode === "hover"));
  } catch { return {}; }
}
