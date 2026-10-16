"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBusiness } from "./BusinessWorkspace";
import { takeTitleFocus } from "./bandeja-order";

/**
 * The one receipt review page: a way back, the record's name and standing,
 * then the source on the left and the fields with their one action on the
 * right. On a phone the source comes first and the fields follow. Every
 * state of a receipt renders inside this frame, read or not, prepared or not.
 */
export default function ReceiptReviewFrame({ recordId, back, eyebrow, title, badge, summary, source, children }: {
  recordId: string;
  back: "inbox" | "expenses";
  eyebrow?: ReactNode;
  title: ReactNode;
  badge?: ReactNode;
  summary?: ReactNode;
  source: ReactNode;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (takeTitleFocus(recordId)) heading.current?.focus();
  }, [recordId]);
  return (
    <section aria-labelledby="receipt-review-title" data-testid="business-record-review">
      <button type="button" onClick={() => openPanel({ kind: back })} className="mb-4 flex min-h-11 items-center gap-1.5 rounded-full pr-3 text-[14px] text-black/65 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:text-white/65">
        <ArrowLeft className="h-4 w-4" aria-hidden="true" />
        {back === "expenses" ? t("business.nav.expenses", "Expenses") : t("business.nav.inbox", "Inbox")}
      </button>
      <header className="mb-5">
        {eyebrow ? <p className="mb-2 text-[13px] text-black/55 dark:text-white/55">{eyebrow}</p> : null}
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="receipt-review-title" ref={heading} tabIndex={-1} className="-mx-1.5 min-w-0 break-words rounded-md px-1.5 font-display focus:outline-none focus:ring-2 focus:ring-black/20 dark:focus:ring-white/30 text-[25px] font-medium tracking-tight text-black dark:text-white">{title}</h2>
          {badge}
        </div>
        {summary ? <div className="mt-3 flex flex-wrap items-baseline gap-x-3 gap-y-1">{summary}</div> : null}
      </header>
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <div className="min-w-0 space-y-4" data-testid="receipt-review-source">{source}</div>
        <div className="min-w-0 space-y-4" data-testid="receipt-review-fields">{children}</div>
      </div>
    </section>
  );
}
