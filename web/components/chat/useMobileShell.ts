"use client";

import { useCallback, useEffect, useState } from "react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import type { SidebarMode } from "@/components/sidebar/ChatSidebar";
import { readStored, writeStored } from "@/lib/browser-storage";
import type { ResponsiveLayout } from "@/lib/responsive-layout";

export type MobileShell = ResponsiveLayout & {
  /** Off-canvas drawer visibility, distinct from the desktop rail's expanded state. */
  isDrawerOpen: boolean;
  openDrawer: () => void;
  closeDrawer: () => void;
};

/**
 * Mobile shell state for the chat surface.
 *
 * The drawer keeps its own open flag rather than reusing the rail's expanded
 * state: a desktop user with an expanded rail who narrows the window must not
 * find a drawer already covering the conversation.
 */
/** Which business navigation band this width uses, and how the rail behaves there. */
export function businessShellLayout(
  workspaceId: string | undefined,
  belowTablet: boolean,
  belowDesktop: boolean,
  sidebarOpen: boolean,
) {
  const businessShell = workspaceId === "business";
  const businessPhone = businessShell && belowTablet;
  const businessTabletStrip = businessShell && !belowTablet && belowDesktop;
  const nav = !businessShell ? undefined : businessPhone ? "phone" : businessTabletStrip ? "tablet" : "desktop";
  return {
    businessShell,
    businessPhone,
    businessTabletStrip,
    nav,
    sidebarCollapsed: businessTabletStrip ? true : !(belowTablet ? true : sidebarOpen),
    railLocked: businessTabletStrip,
    sidebarIsOpen: businessTabletStrip ? false : belowTablet ? true : sidebarOpen,
  };
}

/**
 * Rail open state and the saved rail preference. Business opens labeled and
 * only its toggle collapses it. The personal preference shares this origin's
 * storage, so a saved "collapsed" or "hover" must not reach the Business rail.
 */
export function useSidebarRail(workspaceId: string | undefined) {
  const business = workspaceId === "business";
  const [isSidebarOpen, setIsSidebarOpen] = useState(business);
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>(business ? "expanded" : "collapsed");

  useEffect(() => {
    if (business) return;
    const saved = readStored("argus:sidebar_mode") as SidebarMode | null;
    if (saved === "expanded" || saved === "collapsed" || saved === "hover") {
      setSidebarMode(saved);
      setIsSidebarOpen(saved === "expanded");
    }
  }, [business]);

  const chooseSidebarMode = useCallback((mode: SidebarMode) => {
    setSidebarMode(mode);
    writeStored("argus:sidebar_mode", mode);
    setIsSidebarOpen(mode === "expanded");
  }, []);
  const toggleSidebar = useCallback(() => setIsSidebarOpen((open) => !open), []);
  const closeRailForDialog = useCallback(() => {
    if (!business) setIsSidebarOpen(false);
  }, [business]);

  return { isSidebarOpen, setIsSidebarOpen, sidebarMode, chooseSidebarMode, toggleSidebar, closeRailForDialog };
}

export function useMobileShell(): MobileShell {
  const layout = useResponsiveLayout();
  const [isDrawerOpen, setIsDrawerOpen] = useState(false);

  useEffect(() => {
    if (!layout.isBelowTablet) setIsDrawerOpen(false);
  }, [layout.isBelowTablet]);

  const openDrawer = useCallback(() => setIsDrawerOpen(true), []);
  const closeDrawer = useCallback(() => setIsDrawerOpen(false), []);

  return { ...layout, isDrawerOpen, openDrawer, closeDrawer };
}
