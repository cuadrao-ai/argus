"use client";

import { useEffect } from "react";

/** The widest a ledger grows, its 2rem gutters included; the top bar lines up with the column inside them. */
const WIDE_CANVAS = { max: "90rem", column: "86rem" } as const;

/**
 * A ledger needs the canvas. While a wide screen is showing, the workspace
 * column grows past its reading width and the top bar's search and avatar
 * line up with it. Every other screen keeps the defaults the shell declares.
 */
export function useWideCanvas(active = true) {
  useEffect(() => {
    if (!active) return undefined;
    const root = document.documentElement.style;
    root.setProperty("--cuadrao-canvas-max", WIDE_CANVAS.max);
    root.setProperty("--cuadrao-canvas-column", WIDE_CANVAS.column);
    return () => {
      root.removeProperty("--cuadrao-canvas-max");
      root.removeProperty("--cuadrao-canvas-column");
    };
  }, [active]);
}
