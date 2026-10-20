"use client";

import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download } from "lucide-react";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { countPorRevisar, countStillReading, countUnreadable } from "@/lib/business-review-count";
import { useBusiness } from "./BusinessWorkspace";
import { useForwardAddress } from "./useForwardAddress";
import { cardClass, pillButtonClass } from "./business-ui";
import BusinessMonthClosePanel, { INICIO_EXPORT_ID } from "./BusinessMonthClosePanel";
import { CopyButton, useCopyLabels } from "./foundation/CopyButton";
import { ToastNotice, type QueuedToast } from "./foundation/ToastNotice";

/** The Inicio action row: four pills fit one row from 1024px; 44px tall like every target. */
const actionPill = "inline-flex min-h-11 items-center justify-center gap-1.5 rounded-full px-3.5 text-[14px] font-medium transition-opacity hover:opacity-85 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:focus-visible:ring-white/30";

export default function BusinessOverviewPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, actions, chosen, bridge } = useBusiness();
  const owner = chosen?.role !== "accountant";
  const upload = owner ? actions.create?.find((action) => action.id === "upload_receipt") ?? null : null;
  const recordExpense = owner ? actions.create?.find((action) => action.id === "record_expense") ?? null : null;
  const forwardAddress = useForwardAddress();
  const [toast, setToast] = useState<QueuedToast | null>(null);
  const items = records.inbox;
  const porRevisar = items ? countPorRevisar(items) : null;
  const reading = items ? countStillReading(items) : 0;
  const problem = items ? countUnreadable(items) : 0;
  const primaryClass = `${pillButtonClass} min-w-11 bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`;
  const name = bridge?.greetingName?.trim();
  const greeting = name ? t("business.overview.greeting", { name, defaultValue: "Welcome, {{name}}" }) : t("business.overview.greeting_unnamed", "Welcome");

  const showExport = () => {
    const target = document.getElementById(INICIO_EXPORT_ID);
    if (!target) return;
    const reduce = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    target.scrollIntoView({ behavior: reduce ? "auto" : "smooth", block: "start" });
    target.focus({ preventScroll: true });
  };
  const copyLabels = useCopyLabels(forwardAddress ?? "");

  return (
    <section aria-labelledby="business-overview-title">
      <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
        {greeting}
      </h2>
      <div data-testid="inicio-actions" className={`mb-6 mt-4 ${isBelowTablet ? "flex flex-col gap-2" : "flex flex-wrap items-center gap-2"}`}>
        {upload ? (
          <button type="button" data-testid="business-primary-upload" data-primary="true" className={`${actionPill} bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`} onClick={upload.run}>
            <upload.icon className="h-4 w-4" aria-hidden="true" />
            {upload.label}
          </button>
        ) : chosen?.role === "accountant" ? (
          <button type="button" data-testid="inicio-primary-review" data-primary="true" className={primaryClass} onClick={() => openPanel({ kind: "inbox" })}>
            {t("business.actions.review_receipts", "Review receipts")}
          </button>
        ) : null}
        {recordExpense ? (
          <button type="button" data-testid="inicio-record-expense" className={`${actionPill} border border-black/10 bg-white text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white`} onClick={recordExpense.run}>
            <recordExpense.icon className="h-4 w-4" aria-hidden="true" />
            {recordExpense.label}
          </button>
        ) : null}
        <button type="button" data-testid="inicio-export" className={`${actionPill} border border-black/10 bg-white text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white`} onClick={showExport}>
          <Download className="h-4 w-4" aria-hidden="true" />
          {t("business.overview.export_records", "Export records")}
        </button>
        {owner && forwardAddress ? (
          <CopyButton
            value={forwardAddress}
            label={t("business.overview.copy_forward", "Copy forwarding address")}
            {...copyLabels}
            onFailed={() => setToast({ id: Date.now(), kind: "error", text: copyLabels.failedLabel })}
            testId="inicio-forward-copy"
            className={`${actionPill} border border-black/10 bg-white text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white`}
          >
            {t("business.overview.copy_forward", "Copy forwarding address")}
          </CopyButton>
        ) : null}
      </div>

      <button
        type="button"
        data-testid="inicio-por-revisar"
        onClick={() => openPanel({ kind: "inbox" })}
        className={`${cardClass} mb-6 flex min-h-11 w-full flex-col items-start justify-center text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40`}
      >
        <span className="font-display text-[20px] font-medium text-black dark:text-white">
          {porRevisar === null
            ? t("business.overview.open_inbox", "Open inbox")
            : porRevisar === 0
              ? t("business.overview.por_revisar_none", "Nothing to review")
              : <><span data-testid="inicio-por-revisar-count">{porRevisar}</span>{" "}{t("business.overview.por_revisar", "to review")}</>}
        </span>
        {reading > 0 || problem > 0 ? (
          <span data-testid="inicio-otras" className="mt-1 text-[14px] text-black/70 dark:text-white/75">
            {[
              reading > 0 ? t("business.overview.reading", { count: reading }) : null,
              problem > 0 ? t("business.overview.problem", { count: problem }) : null,
            ].filter(Boolean).join(" · ")}
          </span>
        ) : null}
      </button>

      <BusinessMonthClosePanel />

      {records.error ? (
        <div role="alert" className={`${cardClass} mt-6 text-[14px] text-black/70 dark:text-white/70`}>
          {t("business.overview.error", "We couldn't load your business records. Your saved receipts and expenses are safe. Try again.")}
        </div>
      ) : null}

      {toast ? <ToastNotice key={toast.id} text={toast.text} kind={toast.kind} onClose={() => setToast(null)} /> : null}
    </section>
  );
}
