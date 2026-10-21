"use client";

import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { countNeedsAttention, countStillReading } from "@/lib/business-review-count";
import { inboxCount } from "./inbox-count";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import { EmptyState } from "./foundation/EmptyState";
import { cardClass } from "./business-ui";
import BusinessMonthClosePanel, { useMonthCloseSource } from "./BusinessMonthClosePanel";

/**
 * Inicio: a greeting, then what it takes to close the month. Its actions live
 * in the top bar's Agregar from the tablet stop up; a phone keeps Agregar at
 * the top of the screen.
 */
export default function BusinessOverviewPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, bridge, reload } = useBusiness();
  const items = records.inbox;
  const porRevisar = inboxCount(records);
  const reading = items ? countStillReading(items) : 0;
  const problem = items ? countNeedsAttention(items) : 0;
  const name = bridge?.greetingName?.trim();
  const greeting = name ? t("business.overview.greeting", { name, defaultValue: "Welcome, {{name}}" }) : t("business.overview.greeting_unnamed", "Welcome");
  const monthClose = useMonthCloseSource();

  return (
    <section aria-labelledby="business-overview-title">
      <BusinessMonthClosePanel
        monthClose={monthClose}
        header={(switcher) => (
          <>
            {/* The greeting and the month share one row; a phone wraps the month under it. */}
            <div data-testid="inicio-greeting-row" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
                {greeting}
              </h2>
              {switcher}
            </div>
            {isBelowTablet ? <div data-testid="inicio-actions"><BusinessAddMenu placement="page" /></div> : null}
          </>
        )}
        review={porRevisar === null ? null : {
          count: porRevisar,
          detail: [
            reading > 0 ? t("business.overview.reading", { count: reading }) : null,
            problem > 0 ? t("business.overview.problem", { count: problem }) : null,
          ].filter(Boolean).join(" · ") || null,
          open: () => openPanel({ kind: "inbox" }),
        }}
      />

      {records.error ? (
        <div className={`${cardClass} mt-6`}>
          <EmptyState kind="error" compact testId="inicio-error" title={t("business.empty.overview_error", "We couldn't load your business")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: reload }} />
        </div>
      ) : null}
    </section>
  );
}
