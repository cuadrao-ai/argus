"use client";

import { useEffect, useState } from "react";
import { remainingRetryAfterSeconds, shouldKeepRetryAfterTicker } from "./retry-after";

export function useRetryAfterCountdown(availableAtMs?: number): number {
  const [nowMs, setNowMs] = useState(() => Date.now());

  useEffect(() => {
    const tick = () => {
      const nextNowMs = Date.now();
      setNowMs(nextNowMs);
      return shouldKeepRetryAfterTicker(availableAtMs, nextNowMs);
    };
    if (!tick()) {
      return;
    }
    const id = window.setInterval(() => {
      if (!tick()) {
        window.clearInterval(id);
      }
    }, 250);
    return () => window.clearInterval(id);
  }, [availableAtMs]);

  return remainingRetryAfterSeconds(availableAtMs, nowMs);
}
