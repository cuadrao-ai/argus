"use client";

import { useEffect, useRef, useState } from "react";
import type { LucideIcon } from "lucide-react";

export type StarterSelectionMetadata = {
  strategy_category: "buy_and_hold" | "dca_accumulation";
};

type StarterActionsProps = {
  onSelect: (value: string, metadata?: StarterSelectionMetadata) => void;
  disabled?: boolean;
  /**
   * `wrap` centers the pills under the composer. `scroll` is the narrow-screen
   * form: one row that scrolls sideways. It still centers whenever the pills
   * fit, and only becomes a carousel once they do not.
   */
  layout?: "wrap" | "scroll";
  /**
   * A workspace's own chips. Each one runs its own action, which may open a
   * flow or prepare an editable question; none of them sends on its own.
   */
  entries?: readonly WorkspaceStarterEntry[];
};

export type WorkspaceStarterEntry = {
  key: string;
  icon: LucideIcon | null;
  label: string;
  onSelect: () => void;
};

const wrapPillClassName =
  "flex min-h-11 items-center gap-2 rounded-full border border-black/10 bg-white/50 px-4 py-2 text-[14px] font-medium text-black transition-colors hover:bg-black/5 disabled:opacity-50 dark:border-white/10 dark:bg-[#1f2225]/50 dark:text-white dark:hover:bg-white/5";

const scrollPillClassName =
  "flex min-h-11 shrink-0 snap-start items-center gap-2 whitespace-nowrap rounded-full border border-black/10 bg-white/50 px-3.5 text-[13px] font-medium text-black transition-colors hover:bg-black/5 disabled:opacity-50 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/10 dark:bg-[#1f2225]/50 dark:text-white dark:hover:bg-white/5 dark:focus-visible:ring-white/30";

export default function StarterActions({
  disabled = false,
  layout = "wrap",
  entries: workspaceEntries,
}: StarterActionsProps) {
  // The trailing peek is a promise that more pills exist, so it may only appear
  // when they actually do. Overflow is a measured fact, not a width guess.
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [isOverflowing, setIsOverflowing] = useState(false);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const sync = () =>
      setIsOverflowing(scroller.scrollWidth > scroller.clientWidth + 1);
    sync();
    const observer = new ResizeObserver(sync);
    observer.observe(scroller);
    for (const child of Array.from(scroller.children)) observer.observe(child);
    return () => observer.disconnect();
  }, [layout, workspaceEntries]);

  if (!workspaceEntries?.length) return null;

  const pills = workspaceEntries.map(({ key, icon, label, onSelect: select }) => ({
    key,
    icon,
    label,
    select,
  }));
  const isScroll = layout === "scroll";

  return (
    <div
      ref={scrollerRef}
      data-testid="starter-actions"
      data-starter-layout={layout}
      data-starter-overflowing={isScroll ? String(isOverflowing) : undefined}
      className={
        isScroll
          ? // `safe center` centers the row while it fits and falls back to
            // start once it overflows, so the first pill never becomes
            // unreachable off the leading edge.
            // No trailing padding here: it would widen scrollWidth and make
            // the overflow measurement depend on its own result.
            `argus-scrollbar flex snap-x items-center gap-2 overflow-x-auto pb-1 [justify-content:safe_center] ${
              isOverflowing ? "argus-starter-peek" : ""
            }`
          : "mt-6 flex flex-wrap items-center justify-center gap-3"
      }
    >
      {pills.map(({ key, icon: Icon, label, select }) => (
        <button
          key={key}
          type="button"
          disabled={disabled}
          onClick={select}
          className={isScroll ? scrollPillClassName : wrapPillClassName}
        >
          {Icon ? (
            <Icon className="h-4 w-4 shrink-0 text-black/60 dark:text-white/60" />
          ) : null}
          {label}
        </button>
      ))}
    </div>
  );
}
