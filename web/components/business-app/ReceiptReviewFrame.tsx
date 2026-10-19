"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBusiness } from "./BusinessWorkspace";
import { takeTitleFocus } from "./bandeja-order";

/**
 * The one receipt review page: a way back, then the supplier, the total and
 * the status before anything else. The fields come first in reading order;
 * on a desktop the source sits to their left. The footer spans the pane and sticks to its bottom edge.
 * Every state of a receipt renders inside this frame, read or not, prepared
 * or not.
 */
export default function ReceiptReviewFrame({ recordId, back, title, badge, amount, source, children, history, footer }: {
  recordId: string;
  back: "inbox" | "expenses";
  title: ReactNode;
  badge?: ReactNode;
  /** The formatted total; absent while it is unknown, never a zero. */
  amount?: string | null;
  source: ReactNode;
  children: ReactNode;
  /** Under the fields on a desktop; last of all on a phone. */
  history?: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const heading = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    if (takeTitleFocus(recordId)) heading.current?.focus();
  }, [recordId]);
  return (
    <section aria-labelledby="receipt-review-title" data-testid="business-record-review">
      <button type="button" onClick={() => openPanel({ kind: back })} className="mb-4 flex min-h-11 items-center gap-2 rounded-full pr-3 text-[15px] text-[#56635e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70">
        <ArrowLeft className="h-5 w-5" aria-hidden="true" />
        {back === "expenses" ? t("business.nav.expenses", "Expenses") : t("business.nav.inbox", "Inbox")}
      </button>
      <header className="mb-6" data-testid="receipt-top-block">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="receipt-review-title" ref={heading} tabIndex={-1} className="min-w-0 break-words rounded-[12px] font-display text-[22px] font-medium leading-7 text-[#172b26] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white">{title}</h2>
          {badge}
        </div>
        {amount ? <p data-testid="receipt-total" className="mt-2 text-[28px] font-medium leading-[34px] tabular-nums text-[#172b26] dark:text-white">{amount}</p> : null}
      </header>
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(280px,1fr)_minmax(0,640px)] desktop:grid-rows-[auto_1fr] desktop:gap-6">
        <div className="min-w-0 space-y-4 desktop:col-start-2 desktop:row-start-1 desktop:space-y-6" data-testid="receipt-review-fields">{children}</div>
        <div className="min-w-0 space-y-4 desktop:col-start-1 desktop:row-span-2 desktop:row-start-1 desktop:space-y-6" data-testid="receipt-review-source">{source}</div>
        {history ? <div className="min-w-0 desktop:col-start-2 desktop:row-start-2" data-testid="receipt-review-history">{history}</div> : null}
      </div>
      {footer ? (
        // The workspace region pads its bottom by 48px and sticky offsets count from inside that padding; -48px on both puts the footer on the pane's edge.
        <div data-testid="receipt-review-footer" className="sticky bottom-[-48px] z-10 -mx-4 -mb-12 mt-6 border-t border-[#DCE0DA] bg-[#FFFEFA] px-6 py-4 tablet:-mx-8 dark:border-white/10 dark:bg-[#1f2225]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}
