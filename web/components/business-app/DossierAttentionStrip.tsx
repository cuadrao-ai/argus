"use client";

import { CircleAlert } from "lucide-react";
import { flushSync } from "react-dom";
import { useTranslation } from "react-i18next";
import type { AttentionItem } from "./dossier-attention";

type AttentionField = NonNullable<AttentionItem["field"]>;

/**
 * Opens the field's row for someone who can edit it, scrolls to it and puts
 * focus on what is missing. A row that stays closed takes focus on its control,
 * or on itself when it has none.
 */
function goToField(from: HTMLElement | null, field: AttentionField, onOpen?: (row: AttentionField) => void) {
  const scope = from?.closest('[data-testid="business-record-review"]') ?? document;
  const row = scope.querySelector<HTMLElement>(`[data-fact="${field}"]`);
  if (!row) return;
  // The field has to be on the page before focus can land on it.
  if (onOpen) flushSync(() => onOpen(field));
  row.scrollIntoView?.({ block: "center", behavior: "smooth" });
  const control = row.querySelector<HTMLElement>(field === "currency" ? "select:not(:disabled)" : "input:not(:disabled), select:not(:disabled)") ?? row.querySelector<HTMLElement>("button:not(:disabled), a[href]");
  if (control) control.focus({ preventScroll: true });
  else {
    row.tabIndex = -1;
    row.focus({ preventScroll: true });
  }
}

export default function DossierAttentionStrip({ items, onOpen }: {
  items: readonly AttentionItem[];
  /** Absent for someone who cannot edit the record now. */
  onOpen?: (row: AttentionField) => void;
}) {
  const { t } = useTranslation();
  if (!items.length) return null;
  return (
    <section data-testid="dossier-attention" aria-labelledby="dossier-attention-title" className="rounded-surface border border-[#e6c9a8] bg-[#fdf6ec] px-4 py-3 dark:border-[#6b5235] dark:bg-[#2a241c]">
      <h3 id="dossier-attention-title" className="flex items-center gap-2 text-[14px] font-medium leading-5 text-[#172b26] dark:text-white">
        <CircleAlert className="h-4 w-4 shrink-0 text-[#9a5b13] dark:text-[#e8b26f]" aria-hidden="true" />
        {t("business.dossier.placeholder.blocks_title", "Needed to approve")}
      </h3>
      <ul className="-mx-2 mt-1.5">
        {items.map((item) => (
          <li key={item.key} data-field={item.field ?? undefined}>
            {item.field ? (
              <button type="button" onClick={(event) => goToField(event.currentTarget, item.field!, onOpen)} className="min-h-8 w-full rounded-item px-2 py-1 text-left text-[14px] leading-5 text-[#172b26] underline-offset-2 hover:bg-black/[0.04] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white dark:hover:bg-white/[0.06]">
                {item.text}
              </button>
            ) : (
              <p className="px-2 py-1 text-[14px] leading-5 text-[#172b26] dark:text-white">{item.text}</p>
            )}
          </li>
        ))}
      </ul>
    </section>
  );
}
