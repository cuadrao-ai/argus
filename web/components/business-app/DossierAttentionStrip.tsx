"use client";

import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { AttentionItem } from "./dossier-attention";

/** The rows an item's field points at; the fiscal number is whichever of its rows the form shows. */
export function attentionSelector(field: NonNullable<AttentionItem["field"]>): string {
  return field === "fiscal" ? '[data-fact="ncf"], [data-fact="ecf"], [data-fact="fiscal_number"]' : `[data-fact="${field}"]`;
}

/** Scrolls the field's row into view and puts focus on its control, or on the row when it has none. */
export function goToField(from: HTMLElement | null, field: NonNullable<AttentionItem["field"]>) {
  const scope = from?.closest('[data-testid="business-record-review"]') ?? document;
  const row = scope.querySelector<HTMLElement>(attentionSelector(field));
  if (!row) return;
  row.scrollIntoView?.({ block: "center", behavior: "smooth" });
  const control = row.querySelector<HTMLElement>("button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href]");
  if (control) control.focus({ preventScroll: true });
  else {
    row.tabIndex = -1;
    row.focus({ preventScroll: true });
  }
}

/** What needs the person, at the top of the form: each item goes to its field. Nothing to do renders nothing. */
export default function DossierAttentionStrip({ items }: { items: readonly AttentionItem[] }) {
  const { t } = useTranslation();
  if (!items.length) return null;
  return (
    <section data-testid="dossier-attention" aria-labelledby="dossier-attention-title" className="rounded-surface border border-[#e6c9a8] bg-[#fdf6ec] px-4 py-3 dark:border-[#6b5235] dark:bg-[#2a241c]">
      <h3 id="dossier-attention-title" className="flex items-center gap-2 text-[14px] font-medium leading-5 text-[#172b26] dark:text-white">
        <CircleAlert className="h-4 w-4 shrink-0 text-[#9a5b13] dark:text-[#e8b26f]" aria-hidden="true" />
        {t("business.dossier.attention.title", { count: items.length, defaultValue: "{{count}} to review" })}
      </h3>
      <ul className="-mx-2 mt-1.5">
        {items.map((item) => (
          <li key={item.key} data-kind={item.kind} data-field={item.field ?? undefined}>
            {item.field ? (
              <button type="button" onClick={(event) => goToField(event.currentTarget, item.field!)} className="min-h-8 w-full rounded-item px-2 py-1 text-left text-[14px] leading-5 text-[#172b26] underline-offset-2 hover:bg-black/[0.04] hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white dark:hover:bg-white/[0.06]">
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
