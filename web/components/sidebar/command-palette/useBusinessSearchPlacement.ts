import { useLayoutEffect, useState, type CSSProperties } from "react";
import { businessSearchPlacement, type LayoutMode } from "./paletteLayout";

export function useBusinessSearchPlacement(active: boolean, layout: LayoutMode): CSSProperties | undefined {
  const [style, setStyle] = useState<CSSProperties>();
  useLayoutEffect(() => {
    if (!active) return;
    const anchor = document.querySelector<HTMLElement>('[data-testid="header-search"]') ?? document.querySelector<HTMLElement>("[data-business-search-anchor]");
    const place = () => {
      const rect = anchor?.getBoundingClientRect();
      setStyle(businessSearchPlacement({ width: window.innerWidth, height: window.innerHeight }, rect ? { right: rect.right, bottom: rect.bottom } : null, layout));
    };
    place();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(place);
    if (anchor) observer?.observe(anchor);
    window.addEventListener("resize", place);
    return () => { observer?.disconnect(); window.removeEventListener("resize", place); };
  }, [active, layout]);
  return active ? style : undefined;
}
