"use client";

import { Search } from "lucide-react";
import { useTranslation } from "react-i18next";

/**
 * The search field in the top bar. It reads like a field and opens the one
 * search on click or ⌘K, so its placeholder can teach what search finds.
 */
export function HeaderSearch({ onOpen }: { onOpen: () => void }) {
  const { t } = useTranslation();
  const command = typeof navigator !== "undefined" && /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
  const label = t("business.search.placeholder", "Search merchant, amount or note");
  // The bar gives search whatever width is left; it drops the shortcut hint, then the words, and never spills past its edge.
  return (
    <div className="@container w-full max-w-[520px]">
      <button
        type="button"
        data-testid="header-search"
        onClick={onOpen}
        aria-label={label}
        aria-keyshortcuts={command ? "Meta+K" : "Control+K"}
        className="flex min-h-11 w-full items-center justify-center gap-2 overflow-hidden rounded-full border border-[#DCE0DA] bg-[#FFFEFA] px-[13px] text-left text-[15px] text-[#56635e] transition-colors hover:border-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] @[12rem]:justify-start @[12rem]:px-4 dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65"
      >
        <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
        <span aria-hidden="true" className="hidden min-w-0 flex-1 truncate @[12rem]:block">{label}</span>
        <kbd aria-hidden="true" className="hidden shrink-0 rounded-mark border border-[#DCE0DA] px-1.5 font-sans text-[12px] text-[#56635e] @[16rem]:inline-flex dark:border-white/15 dark:text-white/60">{command ? "⌘K" : "Ctrl K"}</kbd>
      </button>
    </div>
  );
}
