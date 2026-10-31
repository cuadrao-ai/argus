"use client";

import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { formatBusinessName } from "./business-format";
import { inboxCount, problemCount, readingCount } from "./inbox-count";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import BusinessMonthClosePanel, { useMonthCloseSource, type MonthCloseParts } from "./BusinessMonthClosePanel";
import { cardClass } from "./business-ui";
import { HomeHeading } from "./foundation/HomeHeading";
import { HomeCustomize, HomeSetupLead, HomeWork, useHomeOrder, type HomeSectionKey } from "./inicio/HomeOverviewDraft";

/**
 * Inicio: the greeting (in the top bar from the tablet up, here on a phone), then its three layers in the person's
 * order: Resumen del negocio, Finanzas por mes and Cobros y pagos. The month-close panel loads once and hands over
 * its month and money parts. Agregar lives in the top bar; a phone keeps its page button.
 */
export default function BusinessOverviewPanel() {
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, bridge, reload, chosen, userId } = useBusiness();
  const { t } = useTranslation();
  const porRevisar = inboxCount(records, chosen);
  const reading = readingCount(records) ?? 0;
  const problem = problemCount(records) ?? 0;
  const monthClose = useMonthCloseSource();
  const homeOrder = useHomeOrder(userId, chosen?.space_id);

  const home = (parts: MonthCloseParts) => {
    const sections: Record<HomeSectionKey, React.ReactNode> = { work: <HomeWork />, month: parts.month, money: parts.money };
    return (
      <div data-testid="home-overview" className="w-full space-y-6 pb-6">
        {isBelowTablet ? <HomeHeading name={bridge?.greetingName} business={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} /> : null}
        {parts.receiptStatus ? <div className={cardClass}>{parts.receiptStatus}</div> : null}
        <HomeSetupLead />
        {homeOrder.order.map((key) => <div key={key} data-home-section={key}>{sections[key]}</div>)}
        <div className="flex border-t border-[color:var(--surface-divider)] pt-4"><HomeCustomize order={homeOrder.order} onChange={homeOrder.save} isDefault={homeOrder.isDefault} /></div>
      </div>
    );
  };

  return (
    <section aria-labelledby="business-overview-title">
      {isBelowTablet ? <div data-testid="inicio-actions" className="mb-5 empty:hidden" style={{ paddingTop: 32 }}><BusinessAddMenu placement="page" /></div> : null}
      <BusinessMonthClosePanel
        monthClose={monthClose}
        layout="finance"
        arrange={home}
        receiptStatusPlacement={isBelowTablet ? "lead" : "default"}
        review={records.error ? (records.refused ? { state: "refused", reference: records.failureReference } : { state: "failed", retry: reload, reference: records.failureReference }) : porRevisar === null ? { state: records.inbox === null ? "loading" : "unknown" } : {
          count: porRevisar,
          detail: null,
          reading,
          attention: problem,
          open: () => openPanel({ kind: "inbox" }),
        }}
      />
    </section>
  );
}
