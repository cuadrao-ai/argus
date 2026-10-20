"use client";

import { useRef, type KeyboardEvent } from "react";

export type Segment<K extends string> = { key: K; label: string };

/**
 * The one segmented control: a tinted track with the chosen segment in white.
 * It is a radio group, so arrow keys move the choice and Tab enters on it.
 * `value` null means none is chosen (a typed range is showing instead).
 * `fill` stretches the segments across the track; without it they size to
 * their words and the track scrolls sideways when the row is too narrow.
 */
export function SegmentedControl<K extends string>({ label, segments, value, onChange, fill = false, disabled = false, testId }: {
  label: string;
  segments: readonly Segment<K>[];
  value: K | null;
  onChange: (key: K) => void;
  fill?: boolean;
  disabled?: boolean;
  testId?: string;
}) {
  const group = useRef<HTMLDivElement>(null);
  const focusable = value ?? segments[0]?.key;
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
      className={`flex gap-0.5 rounded-full bg-[#EDECE6] p-1 dark:bg-white/[0.06] ${fill ? "w-full" : "max-w-full overflow-x-auto [scrollbar-width:none]"}`}
    >
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
            onClick={() => onChange(segment.key)}
            onKeyDown={(event) => move(event, index)}
            className={`min-h-11 whitespace-nowrap rounded-full px-4 text-[14px] font-medium transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-[-2px] focus-visible:outline-[#2f5a49] disabled:opacity-50 motion-reduce:transition-none ${fill ? "min-w-0 flex-1 px-2" : "shrink-0"} ${
              checked ? "bg-white text-[#172b26] dark:bg-[#2a2d31] dark:text-white" : "text-[#56635e] hover:text-[#172b26] dark:text-white/60 dark:hover:text-white"
            }`}
          >
            {segment.label}
          </button>
        );
      })}
    </div>
  );
}
