"use client";

import { CornerDownLeft, MessageSquarePlus } from "lucide-react";
import { useTranslation } from "react-i18next";

/**
 * The last row when a search matched nothing: the typed text, offered as a new
 * chat. Nothing runs until the user presses Enter or taps the row. `label`
 * lets a workspace name the chat in its own words.
 */
export function AskArgusRow({ label, text, onAsk }: { label?: string; text: string; onAsk: (text: string) => void }) {
  const { t } = useTranslation();
  return (
    <button type="button" data-ask-argus-row onClick={() => onAsk(text)}
      className="flex min-h-11 w-full items-center gap-3 rounded-[12px] border border-black/5 bg-white/70 px-3 py-2.5 text-left transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:bg-white/[0.03] dark:hover:bg-white/[0.06]">
      <MessageSquarePlus className="h-4 w-4 shrink-0 text-black/40 dark:text-white/40" aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block text-[12px] text-black/45 dark:text-white/45">{label ?? t("command_palette.ask_argus.label", "Ask Argus")}</span>
        <span className="block truncate text-[14px] text-black dark:text-white">{text}</span>
        <span className="sr-only">{t("command_palette.ask_argus.hint")}</span>
      </span>
      <CornerDownLeft className="h-3.5 w-3.5 shrink-0 text-black/30 dark:text-white/30" aria-hidden="true" />
    </button>
  );
}
