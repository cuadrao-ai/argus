"use client";

import { Fragment, useEffect, useRef, useState, type KeyboardEvent, type ReactNode } from "react";
import { ChevronDown, Ellipsis, Info, type LucideIcon } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SwitchIndicator, useOptimisticToggle } from "@/components/ui/Switch";
import { secondaryButtonClass } from "./business-ui";
import { FOCUS_RING } from "./foundation/presentation";

const MENU_ROW = `flex min-h-11 w-full items-center gap-3 rounded-item px-3 py-2 text-left text-[14px] leading-5 disabled:cursor-not-allowed disabled:opacity-50 ${FOCUS_RING}`;
const MENU_ROW_NEUTRAL = "text-[#172b26] hover:bg-black/5 dark:text-white dark:hover:bg-white/5";
const MENU_ROW_DANGER = "text-[#9e2f39] hover:bg-[#f6dfe0]/50 dark:text-[#ec9aa0] dark:hover:bg-[#ec9aa0]/10";
const MENU_ICON = "shrink-0 text-[#56635e] dark:text-white/70";

/** One action in Más: its icon, its label, 44px high. Danger is the red one, kept last. */
export function MenuItem({ icon: Icon, label, onSelect, disabled, danger = false, testId }: { icon: LucideIcon; label: string; onSelect: () => void; disabled?: boolean; danger?: boolean; testId?: string }) {
  return (
    <button type="button" role="menuitem" data-testid={testId} disabled={disabled} onClick={onSelect} className={`${MENU_ROW} ${danger ? MENU_ROW_DANGER : MENU_ROW_NEUTRAL}`}>
      <Icon size={16} className={danger ? "shrink-0" : MENU_ICON} aria-hidden="true" />
      {label}
    </button>
  );
}

/**
 * One on/off decision in Más, the same row with a small switch on the right.
 * The whole row is the control. It flips first like every switch, and while
 * its own change is in flight it stays live so its spinner is not dimmed.
 */
export function MenuCheckItem({ icon: Icon, label, hint, checked, onChange, disabled = false, testId }: { icon: LucideIcon; label: string; hint?: string; checked: boolean; onChange: (next: boolean) => void | Promise<unknown>; disabled?: boolean; testId?: string }) {
  const { on, pending, flip } = useOptimisticToggle(checked, onChange, disabled);
  return (
    <button type="button" role="menuitemcheckbox" aria-checked={on} aria-busy={pending || undefined} data-testid={testId} disabled={disabled && !pending} onClick={flip} className={`${MENU_ROW} ${MENU_ROW_NEUTRAL}`}>
      <Icon size={16} className={MENU_ICON} aria-hidden="true" />
      <span className="min-w-0 flex-1">
        <span className="block">{label}</span>
        {hint ? <span className="block text-[12px] leading-4 text-[#56635e] dark:text-white/70">{hint}</span> : null}
      </span>
      <SwitchIndicator on={on} pending={pending} />
    </button>
  );
}

/** Arrow keys, Home and End walk the rows that can be used; the walk wraps. */
function walkRows(event: KeyboardEvent<HTMLDivElement>) {
  const rows = [...event.currentTarget.querySelectorAll<HTMLElement>('[role^="menuitem"]:not(:disabled)')];
  const at = rows.indexOf(document.activeElement as HTMLElement);
  const moves: Record<string, number | undefined> = { ArrowDown: at + 1, ArrowUp: at - 1, Home: 0, End: rows.length - 1 };
  const next = moves[event.key];
  if (next === undefined || !rows.length) return;
  event.preventDefault();
  rows[(next + rows.length) % rows.length].focus();
}

/**
 * The record's less frequent actions behind one "Más" control in the footer:
 * a menu of groups, each an action or a decision, with a line between groups.
 * Its contents stay mounted while it is closed, so a change in flight inside
 * it (a Personal mark, a note) keeps its state. Escape and a click outside close it.
 * On a phone the trigger is an icon, so the footer's actions fit one row when their
 * labels are short and wrap when they are not, and the panel spans the footer instead
 * of hanging off the trigger past the screen's edge. Más sits at the footer's left, so
 * its panel opens from the trigger's left edge.
 */
export function ReceiptMoreMenu({ groups }: { groups: ReactNode[] }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const host = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const panel = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return undefined;
    panel.current?.querySelector<HTMLElement>('[role^="menuitem"]:not(:disabled)')?.focus();
    const outside = (event: PointerEvent) => {
      if (!host.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("pointerdown", outside);
    return () => document.removeEventListener("pointerdown", outside);
  }, [open]);
  const shown = groups.filter(Boolean);
  return (
    <div
      ref={host}
      className="mr-auto tablet:relative"
      data-testid="receipt-more"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || !open) return;
        // The menu closes first; the dossier's own Escape waits for the next press.
        event.preventDefault();
        setOpen(false);
        trigger.current?.focus();
      }}
    >
      <button ref={trigger} type="button" aria-haspopup="menu" aria-expanded={open} aria-controls="receipt-more-panel" onClick={() => setOpen((value) => !value)} className={`${secondaryButtonClass} whitespace-nowrap max-tablet:px-3`}>
        <span className="max-tablet:sr-only">{t("common.more", "More")}</span>
        <Ellipsis className="h-5 w-5 tablet:hidden" aria-hidden="true" />
        <ChevronDown className={`h-4 w-4 transition-transform motion-reduce:transition-none max-tablet:hidden ${open ? "rotate-180" : ""}`} aria-hidden="true" />
      </button>
      <div ref={panel} id="receipt-more-panel" role="menu" aria-label={t("common.more", "More")} hidden={!open} onKeyDown={walkRows} className="absolute inset-x-0 bottom-full z-20 mb-2 tablet:right-auto tablet:w-[22rem] rounded-surface border border-[#DCE0DA] bg-[#FFFEFA] p-1.5 shadow-[0_8px_28px_rgba(23,43,38,0.14)] dark:border-white/10 dark:bg-[#1f2225]">
        {shown.map((group, index) => <Fragment key={index}>{index ? <div role="separator" className="my-1.5 h-px bg-[#DCE0DA] dark:bg-white/10" /> : null}{group}</Fragment>)}
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

/** Inside the sticky bar, so the bar cannot cover the sentence. */
function DossierReviewNote({ note }: { note: string }) {
  return <p data-testid="dossier-review-note" className="flex min-w-0 basis-full items-start gap-1.5 break-words text-[12px] leading-4 text-[#56635e] dark:text-white/70"><Info size={14} className="mt-px shrink-0" aria-hidden="true" />{note}</p>;
}

/**
 * The footer's one shape: Más on the left, the record's actions on the right, and between
 * them what is left to do in plain words. A footer whose caller puts Más among its actions
 * still shows it on the left: Más takes the free space after itself.
 */
export default function ReceiptReviewFooter({ status, more, actions, reviewNote }: { status?: ReactNode; more?: ReactNode; actions: ReactNode; reviewNote?: string | null }) {
  return (
    <div className="relative flex flex-wrap items-center justify-between gap-x-3 gap-y-2 tablet:static">
      {reviewNote ? <DossierReviewNote note={reviewNote} /> : null}
      {more}
      {status ? <div className="min-w-0 flex-1 basis-56 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{status}</div> : null}
      <div data-footer-actions="" className={`flex flex-wrap items-center justify-end gap-2.5 ${more ? "" : "flex-1"}`}>{actions}</div>
    </div>
  );
}
