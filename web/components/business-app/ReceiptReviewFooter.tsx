"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ChevronDown, Ellipsis } from "lucide-react";
import { useTranslation } from "react-i18next";
import { secondaryButtonClass } from "./business-ui";

/**
 * The record's less frequent actions behind one "Más" control in the footer.
 * Its contents stay mounted while it is closed, so a change in flight inside
 * it (a Personal mark, a note) keeps its state. Escape and a click outside close it.
 * On a phone the trigger is an icon, so the footer's actions fit one row when their
 * labels are short and wrap when they are not, and the panel spans the footer instead
 * of hanging off the trigger past the screen's edge.
 */
export function ReceiptMoreMenu({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    const outside = (event: PointerEvent) => {
      if (!host.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  return (
    <div
      ref={host}
      className="tablet:relative"
      data-testid="receipt-more"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        // The menu closes first; the dossier's own Escape waits for the next press.
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
      }}
    >
      <button ref={trigger} type="button" aria-expanded={open} aria-controls="receipt-more-panel" onClick={() => setOpen((value) => !value)} className={`${secondaryButtonClass} whitespace-nowrap max-tablet:px-3`}>
        <span className="max-tablet:sr-only">{t("common.more", "More")}</span>
        <Ellipsis className="h-5 w-5 tablet:hidden" aria-hidden="true" />
        <ChevronDown className={`h-4 w-4 transition-transform motion-reduce:transition-none max-tablet:hidden ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      <div id="receipt-more-panel" hidden={!open} className="absolute inset-x-0 bottom-full z-20 mb-2 space-y-3 tablet:left-auto tablet:w-[22rem] rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-3 shadow-[0_8px_28px_rgba(23,43,38,0.14)] dark:border-white/10 dark:bg-[#1f2225]">
        {children}
      </div>
    </div>
  );
}

function usesCommandKey(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPad|iPod/.test(navigator.userAgent);
}

/** The keys that run the footer's primary action: ⌘↵ on Apple keyboards, Ctrl ↵ elsewhere. */
export function usePrimaryKeys(): string {
  const [command, setCommand] = useState(false);
  useEffect(() => setCommand(usesCommandKey()), []);
  return command ? "⌘↵" : "Ctrl ↵";
}

/** Shows `data-keys` after the label; drawn by CSS, so the button's name stays its words. */
export const KEY_HINT_CLASS = "tablet:after:ml-1 tablet:after:rounded-mark tablet:after:border tablet:after:border-white/25 tablet:after:bg-white/10 tablet:after:px-1.5 tablet:after:py-0.5 tablet:after:text-[12px] tablet:after:leading-4 tablet:after:content-[attr(data-keys)]";

/** The footer's one shape: what is left in plain words on the left, the actions on the right. */
export default function ReceiptReviewFooter({ status, actions }: { status?: ReactNode; actions: ReactNode }) {
  return (
    <div className="relative flex flex-wrap items-center justify-end gap-x-4 gap-y-2 tablet:static">
      <div className="min-w-0 flex-1 basis-56 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{status}</div>
      <div className="flex flex-wrap items-center justify-end gap-2">{actions}</div>
    </div>
  );
}
