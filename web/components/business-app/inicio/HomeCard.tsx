"use client";

import type { ReactNode } from "react";

export const HOME_MUTED = "text-[#56635e] dark:text-white/70";
export const HOME_SKELETON = "bg-black/[0.06] dark:bg-white/[0.08] animate-pulse motion-reduce:animate-none";

/**
 * Inicio's card: a 57px header band in the soft header tint over one divider, the same on both cards so their tops
 * and dividers line up, then the body at its natural height. `title` is the band's heading, or `heading` replaces it
 * (the month card's switcher).
 */
export function HomeCard({ testId, title, heading, count = null, action, children, label }: { testId: string; title?: string; heading?: ReactNode; count?: number | null; action?: ReactNode; children: ReactNode; label?: string }) {
  return (
    <section data-testid={testId} aria-label={label} className="min-w-0 self-start overflow-hidden rounded-surface border border-black/[0.06] bg-white dark:border-white/[0.06] dark:bg-[#1f2225]">
      <header data-testid={`${testId}-band`} className="flex h-[57px] items-center gap-2 border-b border-[color:var(--surface-divider)] bg-[color:var(--surface-header)] px-5">
        {heading ?? <h2 className="min-w-0 truncate font-display text-[17px] font-medium text-[#172b26] dark:text-white">{title}</h2>}
        {count !== null && count > 0 ? <span data-testid={`${testId}-count`} className="rounded-full border border-[color:var(--surface-divider)] bg-white px-2 text-[13px] tabular-nums text-[#56635e] dark:bg-white/[0.06] dark:text-white/70">{count}</span> : null}
        {action ? <span className="ml-auto flex shrink-0 items-center">{action}</span> : null}
      </header>
      {children}
    </section>
  );
}
