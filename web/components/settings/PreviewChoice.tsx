"use client";

import { useRef, type KeyboardEvent, type ReactNode } from "react";

/**
 * One choice among a few, each shown as a small drawing of what it does
 * (a theme, the rail's width). A radio group: arrows move and pick, and the
 * pick applies at once, so the surface stays open to compare.
 */

export type PreviewOption<Key extends string> = { key: Key; label: string; preview: ReactNode };

export function PreviewChoice<Key extends string>({
  label,
  value,
  options,
  onChange,
  testId,
}: {
  label: string;
  value: Key;
  options: readonly PreviewOption<Key>[];
  onChange: (key: Key) => void;
  testId?: string;
}) {
  const buttons = useRef<(HTMLButtonElement | null)[]>([]);
  const keys = options.map((option) => option.key);

  const move = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (!step) return;
    event.preventDefault();
    const index = (keys.indexOf(value) + step + keys.length) % keys.length;
    onChange(keys[index]);
    buttons.current[index]?.focus();
  };

  return (
    <div
      role="radiogroup"
      aria-label={label}
      data-testid={testId}
      onKeyDown={move}
      className="grid gap-[13px]"
      style={{ gridTemplateColumns: `repeat(${Math.max(options.length, 3)}, minmax(0, 1fr))` }}
    >
      {options.map((option, index) => {
        const selected = option.key === value;
        return (
          <button
            key={option.key}
            ref={(node) => { buttons.current[index] = node; }}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            data-testid={testId ? `${testId}-${option.key}` : undefined}
            onClick={() => onChange(option.key)}
            className="group flex flex-col gap-2 rounded-item text-left focus-visible:outline-none"
          >
            <span
              className={`relative block aspect-[16/10] w-full overflow-hidden rounded-item border group-focus-visible:outline group-focus-visible:outline-2 group-focus-visible:outline-offset-2 group-focus-visible:outline-[var(--cuadrao-green)] ${
                selected
                  ? "border-transparent outline outline-2 outline-offset-2 outline-[var(--cuadrao-green)]"
                  : "border-[#DCE0DA] transition-colors duration-150 ease-out group-hover:border-[#7d8a84] dark:border-white/10 dark:group-hover:border-white/30"
              }`}
            >
              {option.preview}
            </span>
            <span className="flex items-center gap-2 text-[14px] font-medium text-black dark:text-white">
              <span
                aria-hidden="true"
                className={`grid h-4 w-4 shrink-0 place-items-center rounded-full border ${
                  selected ? "border-[var(--cuadrao-green)]" : "border-[#7d8a84] dark:border-white/40"
                }`}
              >
                {selected ? <span className="h-2 w-2 rounded-full bg-[var(--cuadrao-green)]" /> : null}
              </span>
              {option.label}
            </span>
          </button>
        );
      })}
    </div>
  );
}

/** The app in miniature: a rail, a heading with the green action, and a card of rows. */
export function AppMiniature({ tone, rail = "expanded" }: { tone: "light" | "dark"; rail?: "expanded" | "icons" }) {
  const light = tone === "light";
  const page = light ? "bg-[#F7F5EE]" : "bg-[#141517]";
  const railFill = light ? "bg-[#e9e7df]" : "bg-[#1b1d20]";
  const card = light ? "bg-white" : "bg-[#1f2225]";
  const ink = light ? "bg-[#172b26]/70" : "bg-white/70";
  const line = light ? "bg-[#172b26]/15" : "bg-white/15";
  const icons = rail === "icons";
  return (
    <span className={`absolute inset-0 flex ${page}`}>
      <span className={`flex shrink-0 flex-col gap-1 p-1.5 ${railFill} ${icons ? "w-[10%] items-center" : "w-[24%]"}`}>
        {[0, 1, 2, 3].map((row) => (
          <span key={row} className="flex items-center gap-1">
            <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${row === 0 ? ink : line}`} />
            {icons ? null : <span className={`h-1 rounded-full ${row === 0 ? `w-3/4 ${ink}` : `w-1/2 ${line}`}`} style={{ flex: 1 }} />}
          </span>
        ))}
      </span>
      <span className="flex min-w-0 flex-1 flex-col gap-1.5 p-2">
        <span className="flex items-center justify-between">
          <span className={`h-1.5 w-1/3 rounded-full ${ink}`} />
          <span className="h-2 w-5 rounded-full bg-[#8fcbb0]" />
        </span>
        <span className={`flex flex-1 flex-col gap-1 rounded-mark p-1.5 ${card}`}>
          <span className={`h-1 w-4/5 rounded-full ${line}`} />
          <span className={`h-1 w-3/5 rounded-full ${line}`} />
          <span className={`h-1 w-2/3 rounded-full ${line}`} />
        </span>
      </span>
    </span>
  );
}
