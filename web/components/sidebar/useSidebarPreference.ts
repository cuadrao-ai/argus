"use client";

import { useEffect, useState } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";
import { businessSidebarModes } from "@/lib/sidebar-mode-state";
import type { SidebarMode } from "./ChatSidebar";

export function useSidebarPreference(surface: string | undefined, personId: string | null | undefined) {
  const business = surface === "business";
  const preferenceOwner = business ? personId : null;
  const [isSidebarOpen, setIsSidebarOpen] = useState(business);
  const [sidebarMode, setSidebarMode] = useState<SidebarMode>(business ? "expanded" : "collapsed");
  useEffect(() => {
    const saved = business ? (preferenceOwner ? businessSidebarModes(readStored("cuadrao:business:sidebar_modes"))[preferenceOwner] : null) : readStored("argus:sidebar_mode");
    const mode = saved === "expanded" || saved === "collapsed" || saved === "hover" ? saved : business ? "expanded" : "collapsed";
    setSidebarMode(mode);
    setIsSidebarOpen(mode === "expanded");
  }, [business, preferenceOwner]);
  const handleSetSidebarMode = (mode: SidebarMode) => {
    setSidebarMode(mode);
    setIsSidebarOpen(mode === "expanded");
    if (business) {
      if (personId) writeStored("cuadrao:business:sidebar_modes", JSON.stringify({ ...businessSidebarModes(readStored("cuadrao:business:sidebar_modes")), [personId]: mode }));
    } else writeStored("argus:sidebar_mode", mode);
  };
  const toggleSidebar = () => {
    if (business && sidebarMode !== "hover") handleSetSidebarMode(isSidebarOpen ? "collapsed" : "expanded");
    else setIsSidebarOpen((open) => !open);
  };
  return { isSidebarOpen, setIsSidebarOpen, sidebarMode, handleSetSidebarMode, toggleSidebar };
}
