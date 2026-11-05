"use client";

import { ChevronDown } from "lucide-react";
import type { SelectHTMLAttributes } from "react";

/** The dossier's one field: the height and surface MoneyInput and DatePicker already have. */
export const REVIEW_INPUT_CLASS = "block min-h-11 w-full rounded-item border border-[#7d8a84] bg-[#FFFEFA] px-3 text-[16px] text-[#172b26] transition-colors hover:border-[#2f5a49] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] disabled:cursor-not-allowed disabled:bg-[#eceeea] disabled:text-[#56635e] dark:bg-[#141517] dark:text-white dark:hover:border-white/45 dark:disabled:bg-[#263b35] dark:disabled:text-white/70";

/** The dossier's one select, with room kept for its chevron. */
export function ReviewSelect(select: Omit<SelectHTMLAttributes<HTMLSelectElement>, "className">) {
  return (
    <div className="relative">
      <select {...select} className={`${REVIEW_INPUT_CLASS} appearance-none truncate pr-9`} />
      <ChevronDown className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-[#56635e] dark:text-white/60" aria-hidden="true" />
    </div>
  );
}
