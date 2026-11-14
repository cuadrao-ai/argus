"use client";

import { Check, Loader2, Pencil, X } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { UNKNOWN_VALUE } from "./business-format";

export const AMOUNT_BOX_CLASS = "w-[min(6.5rem,calc(100%_-_5.5rem))] tablet:w-[min(10rem,calc(100%_-_5.5rem))] min-w-0 shrink-0";

const FOCUS_RING = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49]";
const ACTION_CLASS = `flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-black/[0.04] disabled:opacity-40 dark:hover:bg-white/[0.06] ${FOCUS_RING}`;
const ROW_BLEED = "-my-[11px]";
const IN_PENCIL_COLUMN = "mr-[calc((0.875rem-2.75rem)/2)]";
const PENCIL_CLASS = "h-3.5 w-3.5 shrink-0 text-[#56635e] group-hover:opacity-100 group-focus-visible:opacity-100 dark:text-white/60";

/** What a closed row shows. */
export type RowShown = {
  /** The row's name, for its controls. */
  label: string;
  value: ReactNode;
  /** The value holds controls of its own, so the pencil sits beside it instead of wrapping it. */
  compound?: boolean;
  /** False when the value's own control already opens the row. */
  pencil?: boolean;
  layout?: "amount" | "currency";
};

/**
 * One fact on an open draft, as the profile name editor works: the pencil turns
 * the row into its field with a check and an X. The check or Enter saves. The X
 * or Escape cancels. A locked row holds an edit whose outcome is unknown, so it
 * cannot be dropped.
 */
export default function ReceiptEditRow({ label, value, compound, pencil = true, layout, open, saving, locked, onOpen, onSave, onCancel, children }: RowShown & {
  open: boolean;
  saving: boolean;
  locked: boolean;
  /** Absent for someone who cannot edit the record now. */
  onOpen?: () => void;
  onSave: () => void;
  onCancel: () => void;
  /** The row's field. */
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const numeric = layout === "amount";
  const numberBox = AMOUNT_BOX_CLASS;
  if (open) {
    const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
      // The calendar owns its keys, and the portal of a phone's sheet bubbles here too.
      if ((event.target as Element).closest('[data-testid="date-picker-month"]')) return;
      if (event.key === "Escape") {
        event.stopPropagation();
        if (!locked) onCancel();
      } else if (event.key === "Enter" && (event.target instanceof HTMLInputElement || event.target instanceof HTMLSelectElement)) {
        event.preventDefault();
        onSave();
      }
    };
    const save = t("common.save", "Save");
    const cancel = t("common.cancel", "Cancel");
    return (
      <div data-row-open="" className={numeric ? "flex items-start" : `${ROW_BLEED} flex flex-wrap items-start gap-1 max-tablet:-my-[7px]`} onKeyDown={onKeyDown}>
        <div data-number-box={numeric ? "" : undefined} className={numeric ? numberBox : "min-w-[9.5rem] flex-1"}>{children}</div>
        <div className={numeric ? "flex w-[5.5rem] shrink-0" : `ml-auto flex shrink-0 ${IN_PENCIL_COLUMN}`}>
          <Tooltip content={save} side="top">
            <button type="button" aria-label={`${save} · ${label}`} aria-busy={saving} disabled={saving} className={`${ACTION_CLASS} text-[#2f5a49] dark:text-[#8fcbb0]`} onClick={onSave}>
              {saving ? <Loader2 className="h-[18px] w-[18px] animate-spin motion-reduce:animate-none" aria-hidden="true" /> : <Check className="h-[18px] w-[18px]" aria-hidden="true" />}
            </button>
          </Tooltip>
          <Tooltip content={cancel} side="top">
            <button type="button" aria-label={`${cancel} · ${label}`} disabled={saving || locked} className={`${ACTION_CLASS} text-[#56635e] dark:text-white/60`} onClick={onCancel}>
              <X className="h-[18px] w-[18px]" aria-hidden="true" />
            </button>
          </Tooltip>
        </div>
      </div>
    );
  }
  if (numeric) return <div className="group flex items-start">
    <span data-number-box="" className={`${numberBox} flex h-11 items-center justify-end border border-transparent px-3 text-right text-[16px] leading-6 tabular-nums`}>{value || UNKNOWN_VALUE}</span>
    <span className="flex w-[5.5rem] shrink-0">{onOpen ? <button type="button" onClick={onOpen} aria-label={`${t("business.dossier.edit")} · ${label}`} className={ACTION_CLASS}><Pencil className={`${PENCIL_CLASS} opacity-70`} aria-hidden="true" /></button> : null}</span>
  </div>;
  if (!onOpen) return <>{value || UNKNOWN_VALUE}</>;
  const edit = `${t("business.dossier.edit", "Edit details")} · ${label}`;
  if (compound) {
    return (
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">{value}</div>
        {pencil ? <button type="button" onClick={onOpen} aria-label={edit} className={`group -mr-2 ${ROW_BLEED} flex h-11 w-11 shrink-0 items-center justify-end rounded-item px-2 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] ${FOCUS_RING}`}><Pencil className={`${PENCIL_CLASS} opacity-70`} aria-hidden="true" /></button> : null}
      </div>
    );
  }
  return (
    <button type="button" onClick={onOpen} aria-label={edit} className={`group -mx-2 ${ROW_BLEED} flex min-h-11 w-[calc(100%+1rem)] items-center gap-2 rounded-item px-2 text-left hover:bg-black/[0.04] dark:hover:bg-white/[0.06] ${FOCUS_RING}`}>
      <span className="min-w-0 flex-1">{value || UNKNOWN_VALUE}</span>
      <Pencil className={`${PENCIL_CLASS} ${layout === "currency" ? "opacity-0" : "opacity-70"}`} aria-hidden="true" />
    </button>
  );
}
