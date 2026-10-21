"use client";

import { useState, type ReactNode } from "react";
import { quietButtonClass } from "../business-ui";

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
        <button type="button" data-testid="list-reveal" className={`${quietButtonClass} mt-3`} onClick={() => setShown((count) => count + pageSize)}>
          {revealLabel}
        </button>
      ) : null}
      {canFetch && loadState !== "error" ? (
        <button type="button" data-testid="list-load" disabled={loadState === "loading"} className={`${quietButtonClass} mt-3`} onClick={load}>
          {loadLabel}
        </button>
      ) : null}
      {canFetch && loadState === "error" ? (
        <button type="button" data-testid="list-retry" className={`${quietButtonClass} mt-3`} onClick={load}>
          {retryLabel}
        </button>
      ) : null}
    </div>
  );
}
