"use client";

import type { ButtonHTMLAttributes, ReactNode } from "react";
import { FOCUS_RING } from "./presentation";

const rowActionTarget = `group inline-flex min-h-11 shrink-0 items-center justify-end rounded-full disabled:cursor-not-allowed disabled:opacity-40 ${FOCUS_RING}`;

/** The small outline pill of Abrir in Bandeja. A parent marked `group` lights it on hover. */
export function RowActionLabel({ children }: { children: ReactNode }) {
  return <span className="inline-flex min-h-[30px] min-w-14 items-center justify-center rounded-full border border-black/[0.17] px-2.5 text-[12px] font-medium text-[#56635e] group-hover:bg-black/5 group-hover:text-[#172b26] dark:border-white/[0.17] dark:text-white/70 dark:group-hover:bg-white/5 dark:group-hover:text-white">{children}</span>;
}

/** A quiet action at the right of a row: the pill to the eye, a 44px target to the finger. */
export function RowAction({ children, className = "", ...button }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...button} className={`${rowActionTarget} ${className}`}><RowActionLabel>{children}</RowActionLabel></button>;
}

/** The lesser action beside a pill: plain text with no border, so the two never read as equals. */
export function RowTextAction({ children, className = "", ...button }: ButtonHTMLAttributes<HTMLButtonElement>) {
  return <button type="button" {...button} className={`${rowActionTarget} ${className}`}><span className="inline-flex min-h-[30px] items-center px-2.5 text-[12px] font-medium text-[#56635e] group-hover:text-[#172b26] dark:text-white/70 dark:group-hover:text-white">{children}</span></button>;
}
