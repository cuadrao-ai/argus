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
  return (
    <button
      type="button"
      data-testid="header-search"
      onClick={onOpen}
      aria-keyshortcuts={command ? "Meta+K" : "Control+K"}
      className="flex min-h-11 w-full max-w-[520px] items-center gap-2 rounded-full border border-[#DCE0DA] bg-[#FFFEFA] px-4 text-left text-[15px] text-[#56635e] transition-colors hover:border-[#7d8a84] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:border-white/10 dark:bg-[#1f2225] dark:text-white/65"
    >
      <Search className="h-4 w-4 shrink-0" aria-hidden="true" />
      <span className="min-w-0 flex-1 truncate">{t("business.search.placeholder", "Search merchant, amount or note")}</span>
      <kbd className="shrink-0 rounded-[6px] border border-[#DCE0DA] px-1.5 font-sans text-[12px] text-[#56635e] dark:border-white/15 dark:text-white/60">{command ? "⌘K" : "Ctrl K"}</kbd>
    </button>
  );
}
