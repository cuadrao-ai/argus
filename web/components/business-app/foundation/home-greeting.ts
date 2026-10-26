"use client";

import { useEffect, useState } from "react";

export type GreetingPeriod = "morning" | "afternoon" | "evening" | "late_night";
export type HomeClock = { date: Date; period: GreetingPeriod };

export function greetingPeriod(hour: number): GreetingPeriod {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  if (hour >= 18 && hour < 23) return "evening";
  return "late_night";
}

export function nextGreetingBoundary(date: Date): Date {
  const hour = [5, 12, 18, 23, 24].find((value) => value > date.getHours())!;
  return new Date(date.getFullYear(), date.getMonth(), date.getDate(), hour);
}

export function useHomeClock(active = true): HomeClock | null {
  const [clock, setClock] = useState<HomeClock | null>(null);
  useEffect(() => {
    if (!active) return;
    let timer: number;
    const refresh = () => {
      window.clearTimeout(timer);
      const date = new Date();
      setClock({ date, period: greetingPeriod(date.getHours()) });
      timer = window.setTimeout(refresh, nextGreetingBoundary(date).getTime() - date.getTime());
    };
    const resume = () => { if (document.visibilityState !== "hidden") refresh(); };
    refresh();
    window.addEventListener("focus", refresh);
    document.addEventListener("visibilitychange", resume);
    return () => {
      window.clearTimeout(timer);
      window.removeEventListener("focus", refresh);
      document.removeEventListener("visibilitychange", resume);
    };
  }, [active]);
  return active ? clock : null;
}
