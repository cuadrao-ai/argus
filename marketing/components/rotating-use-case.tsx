"use client";

import { useEffect, useState } from "react";
import styles from "./touchup.module.css";

const INTERVAL_MS = 3400;

export function RotatingUseCase({ phrases }: { phrases: readonly string[] }) {
  const [state, setState] = useState({ current: 0, previous: -1 });

  useEffect(() => {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const timer = window.setInterval(() => {
      if (document.hidden) return;
      setState((s) => ({ current: (s.current + 1) % phrases.length, previous: s.current }));
    }, INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [phrases.length]);

  return (
    <p className={styles.useCase}>
      {state.previous >= 0 && (
        <span key={`out-${state.previous}`} className={styles.useCaseOut} aria-hidden="true">
          {phrases[state.previous]}
        </span>
      )}
      <span key={`in-${state.current}`} className={state.previous >= 0 ? styles.useCaseIn : undefined}>
        {phrases[state.current]}
      </span>
    </p>
  );
}
