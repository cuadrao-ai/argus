"use client";

import { Check, Loader2, Pencil, X } from "lucide-react";
import type { KeyboardEvent, ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Tooltip } from "@/components/ui/Tooltip";
import { UNKNOWN_VALUE } from "./business-format";

const FOCUS_RING = "focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49]";
const ACTION_CLASS = `flex h-11 w-11 shrink-0 items-center justify-center rounded-full hover:bg-black/[0.04] disabled:opacity-40 dark:hover:bg-white/[0.06] ${FOCUS_RING}`;
const PENCIL_CLASS = "h-3.5 w-3.5 shrink-0 text-[#56635e] opacity-70 group-hover:opacity-100 group-focus-visible:opacity-100 dark:text-white/60";

/** What a closed row shows. */
export type RowShown = {
  /** The row's name, for its controls. */
  label: string;
  value: ReactNode;
  /** The value holds controls of its own, so the pencil sits beside it instead of wrapping it. */
  compound?: boolean;
  /** False when the value's own control already opens the row. */
  pencil?: boolean;
};

/**
 * One fact on an open draft, as the profile name editor works: the pencil turns
 * the row into its field with a check and an X. The check or Enter saves. The X
 * or Escape cancels. A locked row holds an edit whose outcome is unknown, so it
 * cannot be dropped.
 */
export default function ReceiptEditRow({ label, value, compound, pencil = true, open, saving, locked, onOpen, onSave, onCancel, children }: RowShown & {
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
      <div data-row-open="" className="-my-[7px] flex flex-wrap items-start gap-x-1 gap-y-1" onKeyDown={onKeyDown}>
        <div className="min-w-[11rem] flex-1">{children}</div>
        <div className="ml-auto flex shrink-0">
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
  if (!onOpen) return <>{value || UNKNOWN_VALUE}</>;
  const edit = `${t("business.dossier.edit", "Edit details")} · ${label}`;
  if (compound) {
    return (
      <div className="flex items-start gap-2">
        <div className="min-w-0 flex-1">{value}</div>
        {pencil ? <button type="button" onClick={onOpen} aria-label={edit} className={`group -mr-2 -mt-[7px] flex h-9 w-9 shrink-0 items-center justify-end rounded-item px-2 hover:bg-black/[0.04] dark:hover:bg-white/[0.06] ${FOCUS_RING}`}><Pencil className={PENCIL_CLASS} aria-hidden="true" /></button> : null}
      </div>
    );
  }
  return (
    <button type="button" onClick={onOpen} aria-label={edit} className={`group -mx-2 -my-[7px] flex min-h-9 w-[calc(100%+1rem)] items-center gap-2 rounded-item px-2 text-left hover:bg-black/[0.04] dark:hover:bg-white/[0.06] ${FOCUS_RING}`}>
      <span className="min-w-0 flex-1">{value || UNKNOWN_VALUE}</span>
      <Pencil className={PENCIL_CLASS} aria-hidden="true" />
    </button>
  );
}
