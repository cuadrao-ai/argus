"use client";

import type { ReactNode } from "react";
import { primaryButtonClass, quietButtonClass, secondaryButtonClass } from "../business-ui";

/**
 * The ways a screen can be empty, each designed on its own:
 * first run (nothing yet: teach what the screen is for), no results (a search
 * found nothing), filtered (records exist outside the current filter), done
 * (the work is finished: say so and offer what comes next, quietly) and error
 * (we could not load: the one kind whose action is to try again).
 */
export type EmptyKind = "first_run" | "no_results" | "filtered" | "done" | "error";

export type EmptyMark = "inbox" | "receipt" | "bell" | "mail" | "calendar" | "check" | "search" | "filter" | "cloud";

export type EmptyAction = { label: string; run: () => void; icon?: ReactNode };

const KIND_MARK: Record<EmptyKind, EmptyMark | null> = { first_run: null, no_results: "search", filtered: "filter", done: "check", error: "cloud" };

export function EmptyState({ kind, mark, title, body, action, secondary, testId, compact = false }: {
  kind: EmptyKind;
  /** The drawing; no results, filtered and error bring their own unless one is named. */
  mark?: EmptyMark;
  title: string;
  body?: string;
  /** The next step the owner would take: add, change the filter, try again. */
  action?: EmptyAction;
  secondary?: EmptyAction;
  testId?: string;
  /** Inside a card or a column: less space around it. */
  compact?: boolean;
}) {
  const drawn = mark ?? KIND_MARK[kind] ?? "inbox";
  return (
    <div
      data-testid={testId}
      data-empty-kind={kind}
      role={kind === "error" ? "alert" : undefined}
      className={`flex flex-col items-center text-center ${compact ? "py-6" : "py-12"}`}
    >
      <EmptyDrawing mark={drawn} tone={kind === "error" ? "error" : "brand"} />
      <h3 className="mt-4 font-display text-[17px] font-medium text-[#172b26] dark:text-white">{title}</h3>
      {body ? <p className="mt-1 max-w-sm text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{body}</p> : null}
      {action || secondary ? (
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          {action ? (
            <button
              type="button"
              onClick={action.run}
              // Changing the filter is an action inside content, never the screen's one primary.
              className={kind === "filtered"
                ? quietButtonClass
                : kind === "error" || kind === "done"
                  ? secondaryButtonClass
                  : primaryButtonClass}
            >
              {action.icon}
              {action.label}
            </button>
          ) : null}
          {secondary ? (
            <button
              type="button"
              onClick={secondary.run}
              className={quietButtonClass}
            >
              {secondary.icon}
              {secondary.label}
            </button>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}

/**
 * Small two-tone drawings: a soft tinted shape under a line drawing in the
 * brand green (red for errors). Placeholders for final art; one per screen.
 */
export function EmptyDrawing({ mark, tone = "brand" }: { mark: EmptyMark; tone?: "brand" | "error" }) {
  const ink = tone === "error" ? "text-[#9e2f39] dark:text-[#ec9aa0]" : "text-[#2f5a49] dark:text-[#8fcbb0]";
  const wash = tone === "error" ? "fill-[#f6dfe0] dark:fill-[#ec9aa0]/15" : "fill-[#e3ebe1] dark:fill-[#8fcbb0]/15";
  const line = { fill: "none", stroke: "currentColor", strokeWidth: 2, strokeLinecap: "round" as const, strokeLinejoin: "round" as const };
  return (
    <svg viewBox="0 0 72 72" width={72} height={72} aria-hidden="true" data-mark={mark} className={ink}>
      <circle cx="36" cy="38" r="30" className={wash} />
      {mark === "inbox" ? (
        <g {...line}>
          <path d="M16 40 L22 22 H50 L56 40" />
          <path d="M16 40 V52 H56 V40 H44 L41 45 H31 L28 40 Z" />
          <path d="M30 30 H42" />
        </g>
      ) : null}
      {mark === "receipt" ? (
        <g {...line}>
          <path d="M24 14 H48 V56 L44 53 L40 56 L36 53 L32 56 L28 53 L24 56 Z" />
          <path d="M30 24 H42 M30 31 H42 M30 38 H38" />
          <path d="M38 46 H42" />
        </g>
      ) : null}
      {mark === "bell" ? (
        <g {...line}>
          <path d="M36 16 C27 16 23 23 23 31 V40 L18 47 H54 L49 40 V31 C49 23 45 16 36 16 Z" />
          <path d="M31 51 C32 55 40 55 41 51" />
        </g>
      ) : null}
      {mark === "mail" ? (
        <g {...line}>
          <rect x="15" y="22" width="42" height="30" rx="4" />
          <path d="M16 25 L36 40 L56 25" />
        </g>
      ) : null}
      {mark === "calendar" ? (
        <g {...line}>
          <rect x="17" y="20" width="38" height="34" rx="4" />
          <path d="M17 30 H55 M27 15 V24 M45 15 V24" />
          <path d="M25 39 H29 M34 39 H38 M43 39 H47 M25 46 H29 M34 46 H38" />
        </g>
      ) : null}
      {mark === "check" ? (
        <g {...line}>
          <circle cx="36" cy="36" r="17" />
          <path d="M28 36 L34 42 L45 30" />
        </g>
      ) : null}
      {mark === "search" ? (
        <g {...line}>
          <circle cx="32" cy="32" r="12" />
          <path d="M41 41 L53 53" />
        </g>
      ) : null}
      {mark === "filter" ? (
        <g {...line}>
          <path d="M17 20 H55 L40 37 V51 L32 55 V37 Z" />
        </g>
      ) : null}
      {mark === "cloud" ? (
        <g {...line}>
          <path d="M24 48 C17 48 14 43 14 38 C14 32 19 28 25 29 C27 22 33 18 40 19 C48 20 52 26 52 32 C57 33 59 37 59 41 C59 45 56 48 51 48 Z" />
          <path d="M33 34 L41 42 M41 34 L33 42" />
        </g>
      ) : null}
    </svg>
  );
}
