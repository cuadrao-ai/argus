import { useLayoutEffect, useState, type CSSProperties } from "react";
import { adaptiveSearchPlacement, businessSearchPlacement, type LayoutMode } from "./paletteLayout";

export function useBusinessSearchPlacement(active: boolean, layout: LayoutMode, adaptive = false): CSSProperties | undefined {
  const [style, setStyle] = useState<CSSProperties>();
  useLayoutEffect(() => {
    if (!active) return;
    const anchor = adaptive
      ? document.querySelector<HTMLElement>('[data-testid="workspace-canvas"]')
      : document.querySelector<HTMLElement>('[data-testid="header-search"]') ?? document.querySelector<HTMLElement>("[data-business-search-anchor]");
    const place = () => {
      const rect = anchor?.getBoundingClientRect();
      const viewport = { width: window.innerWidth, height: window.innerHeight };
      setStyle(adaptive
        ? adaptiveSearchPlacement(viewport, rect ? { left: rect.left, width: rect.width } : null, layout)
        : businessSearchPlacement(viewport, rect ? { right: rect.right, bottom: rect.bottom } : null, layout));
    };
    place();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
    if (anchor) observer?.observe(anchor);
    window.addEventListener("resize", place);
    return () => { observer?.disconnect(); window.removeEventListener("resize", place); };
  }, [active, layout, adaptive]);
  return active ? style : undefined;
}
