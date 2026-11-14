"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from "react";

/** How long a row that just arrived stays marked, counted from the moment the person can see it. */
export const ARRIVAL_HIGHLIGHT_MS = 6000;
/** The list's styles read the same time from here, so the fade and the mark end together. */
const HIGHLIGHT_TIME = "--arrival-highlight";
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

/** The first row the person can see, and where it sits. */
function firstVisibleRow(root: HTMLElement, attribute: string): Anchor | null {
  const edge = scrollerOf(root)?.getBoundingClientRect().top ?? 0;
  const row = [...root.querySelectorAll<HTMLElement>(`[${attribute}]`)].find(node => node.getBoundingClientRect().bottom > edge);
  return row ? { key: row.getAttribute(attribute)!, top: row.getBoundingClientRect().top } : null;
}

const without = (keys: ReadonlySet<string>, gone: readonly string[]): ReadonlySet<string> => gone.some(key => keys.has(key)) ? new Set([...keys].filter(key => !gone.includes(key))) : keys;

/**
 * One rule for a list that updates on its own. `hold` is called just before
 * new rows are applied; after they render, the first row the person was
 * looking at is put back where it was, so a row that lands above it moves
 * nothing in view. `arrived` names the new rows; each is marked for a short
 * time that starts when the person can first see it, so a row that lands in
 * another view, on another page or off screen is still marked when reached.
 * Rows are known by their own key, never by position.
 */
export function useListArrivals(root: RefObject<HTMLElement | null>, attribute: string = LIST_ROW) {
  const [unseen, setUnseen] = useState(NONE);
  const [fresh, setFresh] = useState(NONE);
  const anchor = useRef<Anchor | null>(null);
  const timers = useRef(new Set<ReturnType<typeof setTimeout>>());
  const hold = useCallback(() => { anchor.current = root.current ? firstVisibleRow(root.current, attribute) : null; }, [root, attribute]);
  const arrived = useCallback((keys: readonly string[]) => { if (keys.length) setUnseen(current => new Set([...current, ...keys])); }, []);
  const seen = useCallback((keys: readonly string[]) => {
    root.current?.style.setProperty(HIGHLIGHT_TIME, `${ARRIVAL_HIGHLIGHT_MS}ms`);
    setUnseen(current => without(current, keys));
    setFresh(current => new Set([...current, ...keys]));
    const timer = setTimeout(() => { timers.current.delete(timer); setFresh(current => without(current, keys)); }, ARRIVAL_HIGHLIGHT_MS);
    timers.current.add(timer);
  }, [root]);
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
  // Runs after every render: a row that waits may have just been drawn by a change of view, page or filter.
  useEffect(() => {
    if (!unseen.size || !root.current) return;
    const waiting = [...root.current.querySelectorAll<HTMLElement>(`[${attribute}]`)].filter(node => unseen.has(node.getAttribute(attribute)!));
    if (!waiting.length) return;
    const watcher = new IntersectionObserver(entries => {
      const keys = entries.filter(entry => entry.isIntersecting).map(entry => entry.target.getAttribute(attribute)!);
      if (keys.length) seen(keys);
    });
    for (const row of waiting) watcher.observe(row);
    return () => watcher.disconnect();
  });
  useEffect(() => { const pending = timers.current; return () => { for (const timer of pending) clearTimeout(timer); }; }, []);
  return { fresh, hold, arrived };
}
