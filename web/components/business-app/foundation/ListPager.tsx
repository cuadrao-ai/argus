"use client";

import { useState, type ReactNode } from "react";

export type ListLoad = "idle" | "loading" | "error";

export function ListPager<T>({
  items,
  pageSize,
  load,
  loadState = "idle",
  revealLabel,
  loadLabel,
  retryLabel,
  listClassName,
  listTestId,
  renderItem,
}: {
  items: readonly T[];
  pageSize: number;
  load?: () => void;
  loadState?: ListLoad;
  revealLabel: string;
  loadLabel: string;
  retryLabel: string;
  listClassName?: string;
  listTestId?: string;
  renderItem: (item: T) => ReactNode;
}) {
  const [shown, setShown] = useState(pageSize);
  const visible = items.slice(0, shown);
  const moreLoaded = shown < items.length;
  const canFetch = !moreLoaded && load !== undefined;
  return (
    <div data-testid="list-pager">
      <ul className={listClassName} data-testid={listTestId}>
        {visible.map((item) => renderItem(item))}
      </ul>
      {moreLoaded ? (
        <button type="button" data-testid="list-reveal" className="mt-3 inline-flex min-h-11 items-center rounded-full px-4 text-[16px] font-medium text-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49]" onClick={() => setShown((count) => count + pageSize)}>
          {revealLabel}
        </button>
      ) : null}
      {canFetch && loadState !== "error" ? (
        <button type="button" data-testid="list-load" disabled={loadState === "loading"} className="mt-3 inline-flex min-h-11 items-center rounded-full px-4 text-[16px] font-medium text-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:opacity-50" onClick={load}>
          {loadLabel}
        </button>
      ) : null}
      {canFetch && loadState === "error" ? (
        <button type="button" data-testid="list-retry" className="mt-3 inline-flex min-h-11 items-center rounded-full px-4 text-[16px] font-medium text-[#9e2f39] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#9e2f39]" onClick={load}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
