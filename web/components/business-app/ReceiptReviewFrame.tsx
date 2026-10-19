"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBusiness } from "./BusinessWorkspace";
import { takeTitleFocus } from "./bandeja-order";

/**
 * The one receipt review page: a way back, then the supplier, the total and
 * the status before anything else. On a desktop the source sits on the left
 * and the fields on the right; on a phone the fields come first and the
 * source follows. The footer spans the pane and sticks to its bottom edge.
 * Every state of a receipt renders inside this frame, read or not, prepared
 * or not.
 */
export default function ReceiptReviewFrame({ recordId, back, title, badge, amount, source, children, footer }: {
  recordId: string;
  back: "inbox" | "expenses";
  title: ReactNode;
  badge?: ReactNode;
  /** The formatted total; absent while it is unknown, never a zero. */
  amount?: string | null;
  source: ReactNode;
  children: ReactNode;
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
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(0,1fr)_minmax(0,640px)] desktop:gap-6">
        <div className="order-2 min-w-0 space-y-4 desktop:order-1 desktop:space-y-6" data-testid="receipt-review-source">{source}</div>
        <div className="order-1 min-w-0 space-y-4 desktop:order-2 desktop:space-y-6" data-testid="receipt-review-fields">{children}</div>
      </div>
      {footer ? (
        <div data-testid="receipt-review-footer" className="sticky bottom-0 z-10 -mx-4 mt-6 border-t border-[#DCE0DA] bg-[#FFFEFA] px-6 py-4 tablet:-mx-8 dark:border-white/10 dark:bg-[#1f2225]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}
