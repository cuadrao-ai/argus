"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/** How long a row that just arrived stays marked. */
export const ARRIVAL_HIGHLIGHT_MS = 4000;
/** A list row names itself with an attribute so the list can find it again after rows land above it. This is the name when a list has none of its own. */
const LIST_ROW = "data-list-row";

type Anchor = { key: string; top: number };
const NONE: ReadonlySet<string> = new Set();

/** The nearest ancestor that scrolls; null when the page itself does. */
function scrollerOf(node: HTMLElement): HTMLElement | null {
  for (let parent = node.parentElement; parent; parent = parent.parentElement) {
    const overflow = getComputedStyle(parent).overflowY;
    if ((overflow === "auto" || overflow === "scroll") && parent.scrollHeight > parent.clientHeight) return parent;
  }
  return null;
}

/** The first row the person can see, and where it sits. Null while the start of the list is in view: rows that land there should show. */
function firstVisibleRow(root: HTMLElement, attribute: string): Anchor | null {
  const edge = scrollerOf(root)?.getBoundingClientRect().top ?? 0;
  const rows = [...root.querySelectorAll<HTMLElement>(`[${attribute}]`)];
  const index = rows.findIndex(row => row.getBoundingClientRect().bottom > edge);
  if (index < 0) return null;
  const top = rows[index].getBoundingClientRect().top;
  if (index === 0 && top >= edge) return null;
  return { key: rows[index].getAttribute(attribute)!, top };
}

/**
 * One rule for a list that updates on its own. `hold` is called just before
 * new rows are applied; after they render, the first row the person was
 * looking at is put back where it was. `arrived` marks the new rows for a
 * short time. Rows are known by their own key, never by position.
 */
export function useListArrivals(root: RefObject<HTMLElement | null>, attribute: string = LIST_ROW) {
  const [fresh, setFresh] = useState(NONE);
  const anchor = useRef<Anchor | null>(null);
  const hold = useCallback(() => { anchor.current = root.current ? firstVisibleRow(root.current, attribute) : null; }, [root, attribute]);
  const arrived = useCallback((keys: readonly string[]) => { if (keys.length) setFresh(new Set(keys)); }, []);
  useLayoutEffect(() => {
    const held = anchor.current;
    anchor.current = null;
    if (!held || !root.current) return;
    const row = [...root.current.querySelectorAll<HTMLElement>(`[${attribute}]`)].find(node => node.getAttribute(attribute) === held.key);
    if (!row) return;
    const moved = row.getBoundingClientRect().top - held.top;
    if (!moved) return;
    const scroller = scrollerOf(root.current);
    if (scroller) scroller.scrollTop += moved;
    else window.scrollBy(0, moved);
  });
  useEffect(() => {
    if (!fresh.size) return;
    const timer = setTimeout(() => setFresh(NONE), ARRIVAL_HIGHLIGHT_MS);
    return () => clearTimeout(timer);
  }, [fresh]);
  return { fresh, hold, arrived };
}
