"use client";

import { useEffect, useLayoutEffect, useRef, type KeyboardEvent, type PointerEvent } from "react";
import type { LucideIcon } from "lucide-react";
import { createSpringDriver, LEAD, TRAIL } from "./spring";

/** `count` follows the label in a lighter weight: how many rows the segment holds, or the screen's mark for a count it does not know ("-"), never a 0. */
export type Segment<K extends string> = { key: K; label: string; count?: number | string | null; icon?: LucideIcon };

type Edges = { l: number; r: number };

/** A press reaches this far toward the segment before the release commits it. */
const PRESS_REACH_PX = 14;

/**
 * The one segmented control: a tinted track and one bordered thumb that travels
 * to the chosen segment. The thumb's leading edge moves first and the trailing
 * edge follows on a softer spring, so it stretches by its width (never a
 * scale, which would bend the round ends) and settles with a small bounce.
 * Pressing a segment reaches toward it; releasing commits; sliding off
 * springs back. It is a radio group: arrow keys move the choice.
 * `value` null means none is chosen (a typed range is showing instead).
 * `fill` stretches the segments across the track; without it they size to
 * their words and the track scrolls sideways when the row is too narrow.
 */
export function SegmentedControl<K extends string>({ label, segments, value, onChange, fill = false, stacked = false, disabled = false, testId }: {
  label: string;
  segments: readonly Segment<K>[];
  value: K | null;
  onChange: (key: K) => void;
  fill?: boolean;
  /** Icon above a short word, for a few long labels in a narrow sheet. */
  stacked?: boolean;
  disabled?: boolean;
  testId?: string;
}) {
  const group = useRef<HTMLDivElement>(null);
  const thumb = useRef<HTMLSpanElement>(null);
  const driver = useRef<ReturnType<typeof createSpringDriver<"l" | "r">> | null>(null);
  const placed = useRef(false);
  const focusable = value ?? segments[0]?.key;
  const shape = segments.map((segment) => `${segment.key}:${segment.label}:${segment.count ?? ""}`).join("|");

  const edgesOf = (key: K | null): Edges | null => {
    const node = key === null ? null : group.current?.querySelector<HTMLElement>(`[data-segment="${key}"]`);
    return node ? { l: node.offsetLeft, r: node.offsetLeft + node.offsetWidth } : null;
  };

  useLayoutEffect(() => {
    driver.current = createSpringDriver<"l" | "r">(
      { l: 0, r: 0 },
      // Whichever edge points the way the thumb travels leads; the other trails.
      (key, from, to) => ((key === "r") === (to > from) ? LEAD : TRAIL),
      ({ l, r }) => {
        if (!thumb.current) return;
        thumb.current.style.transform = `translateX(${l}px)`;
        thumb.current.style.width = `${Math.max(0, r - l)}px`;
      },
    );
    return () => driver.current?.stop();
  }, []);

  useLayoutEffect(() => {
    const edges = edgesOf(value);
    if (!edges || !driver.current) return;
    if (placed.current) driver.current.set(edges);
    else driver.current.jump(edges);
    placed.current = true;
    // edgesOf reads the DOM; a change of words moves the segments too.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value, shape]);

  // Only a real change of size snaps the thumb; a new observer's first report is not one.
  const current = useRef(value);
  useLayoutEffect(() => { current.current = value; }, [value]);
  useEffect(() => {
    const node = group.current;
    if (!node || typeof ResizeObserver === "undefined") return undefined;
    let width = node.offsetWidth;
    const observer = new ResizeObserver(() => {
      if (node.offsetWidth === width) return;
      width = node.offsetWidth;
      const edges = edgesOf(current.current);
      if (edges) driver.current?.jump(edges);
    });
    observer.observe(node);
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const reach = (key: K) => {
    const from = edgesOf(value);
    const to = edgesOf(key);
    if (!from || !to || key === value || disabled) return;
    driver.current?.set(to.l > from.l ? { r: from.r + PRESS_REACH_PX } : { l: from.l - PRESS_REACH_PX });
  };
  const settle = () => {
    const edges = edgesOf(value);
    if (edges) driver.current?.set(edges);
  };

  const move = (event: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const next = segments[(index + step + segments.length) % segments.length];
    onChange(next.key);
    group.current?.querySelector<HTMLButtonElement>(`[data-segment="${next.key}"]`)?.focus();
  };

  return (
    <div
      ref={group}
      role="radiogroup"
      aria-label={label}
      data-testid={testId}
      className={`relative gap-0.5 ${stacked ? "rounded-surface" : "rounded-full"} bg-[var(--segment-track)] p-1 ${fill ? "flex w-full" : "inline-flex max-w-full overflow-x-auto [scrollbar-width:none]"}`}
    >
      <span
        ref={thumb}
        aria-hidden="true"
        data-segment-thumb
        className={`pointer-events-none absolute bottom-1 left-0 top-1 ${stacked ? "rounded-item" : "rounded-full"} border border-[var(--segment-thumb-border)] bg-[var(--segment-thumb)] transition-opacity duration-150 ease-out will-change-transform ${value === null ? "opacity-0" : "opacity-100"}`}
      />
      {segments.map((segment, index) => {
        const checked = segment.key === value;
        return (
          <button
            key={segment.key}
            type="button"
            role="radio"
            aria-checked={checked}
            disabled={disabled}
            data-segment={segment.key}
            tabIndex={segment.key === focusable ? 0 : -1}
            onPointerDown={(event: PointerEvent<HTMLButtonElement>) => { if (event.button === 0) reach(segment.key); }}
            // A touch ends with a pointerleave before its click; only a mouse dragged off with the button down takes the reach back.
            onPointerLeave={(event) => { if (event.pointerType === "mouse" && event.buttons === 1) settle(); }}
            onPointerCancel={settle}
            onClick={() => onChange(segment.key)}
            onKeyDown={(event) => move(event, index)}
            className={`relative min-h-11 ${stacked ? "flex flex-col items-center justify-center gap-1 rounded-item py-2 text-[12px] leading-4" : "inline-flex items-center justify-center gap-2 whitespace-nowrap rounded-full text-[14px]"} px-4 font-medium transition-colors duration-200 ease-out focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[var(--cuadrao-green)] disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none ${fill ? "min-w-0 flex-auto px-2" : "shrink-0"} ${
              // Selected: the bordered thumb sits under it. Hover only tints an unchosen segment, with no border, so it never reads as chosen.
              checked ? "text-[var(--segment-text-strong)]" : "text-[var(--segment-text)] enabled:hover:bg-[var(--segment-hover)] enabled:hover:text-[var(--segment-text-strong)]"
            }`}
          >
            {segment.icon ? <segment.icon className="h-4 w-4 shrink-0" aria-hidden="true" /> : null}
            <span className={stacked ? "text-center" : undefined}>{segment.label}</span>
            {segment.count != null ? <span className="-ml-0.5 font-normal tabular-nums text-[var(--segment-text)]">{segment.count}</span> : null}
          </button>
        );
      })}
    </div>
  );
}
