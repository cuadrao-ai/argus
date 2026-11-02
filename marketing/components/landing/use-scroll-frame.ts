"use client";

import { useLayoutEffect } from "react";

export type ScrollFrame = { width: number; height: number; reduced: boolean };

// Calls `paint` once per animation frame while the page scrolls or resizes.
export function useScrollFrame(paint: (frame: ScrollFrame) => void): void {
  useLayoutEffect(() => {
    const motion = window.matchMedia("(prefers-reduced-motion: reduce)");
    let request = 0;
    const run = () => {
      request = 0;
      paint({ width: window.innerWidth, height: window.innerHeight, reduced: motion.matches });
    };
    const schedule = () => {
      if (!request) request = window.requestAnimationFrame(run);
    };
    run();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    motion.addEventListener("change", schedule);
    return () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      motion.removeEventListener("change", schedule);
      window.cancelAnimationFrame(request);
    };
  }, [paint]);
}
