"use client";

import { useEffect, useState } from "react";

const TYPE_INTERVAL_MS = 35;

export function useTypewriter(text: string) {
  const [progress, setProgress] = useState({ text, count: 0 });
  const visibleCount = progress.text === text ? progress.count : 0;

  useEffect(() => {
    const motion = window.matchMedia?.("(prefers-reduced-motion: reduce)");
    let interval: number | undefined;
    const complete = () => {
      window.clearInterval(interval);
      setProgress({ text, count: text.length });
    };
    const onMotionChange = () => {
      if (motion?.matches) complete();
    };

    if (motion?.matches || !text) {
      complete();
    } else {
      let count = 0;
      setProgress({ text, count });
      interval = window.setInterval(() => {
        count += 1;
        setProgress({ text, count });
        if (count >= text.length) window.clearInterval(interval);
      }, TYPE_INTERVAL_MS);
    }
    motion?.addEventListener("change", onMotionChange);
    return () => {
      window.clearInterval(interval);
      motion?.removeEventListener("change", onMotionChange);
    };
  }, [text]);

  return { visibleCount, done: visibleCount >= text.length };
}
