import { useEffect, useState } from "react";
import { readStored, writeStored } from "@/lib/browser-storage";
import type { LayoutMode } from "./paletteLayout";

/** The palette's chosen width (results alone, or beside a preview), remembered in this browser across visits. */
export function usePaletteLayoutMode() {
  const [layoutMode, setLayoutMode] = useState<LayoutMode>("expanded");
  useEffect(() => {
    const saved = readStored("argus:command_palette_layout");
    if (saved === "expanded" || saved === "collapsed") setLayoutMode(saved);
  }, []);
  const toggleLayout = () => {
    setLayoutMode((current) => {
      const next = current === "expanded" ? "collapsed" : "expanded";
      writeStored("argus:command_palette_layout", next);
      return next;
    });
  };
  return { layoutMode, setLayoutMode, toggleLayout };
}
