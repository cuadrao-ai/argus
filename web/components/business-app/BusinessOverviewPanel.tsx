"use client";

import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { businessSettlementAvailable } from "@/lib/business-api";
import { formatBusinessName } from "./business-format";
import { inboxCount, readingCount } from "./inbox-count";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import BusinessMonthClosePanel, { useMonthCloseSource, type MonthCloseParts } from "./BusinessMonthClosePanel";
import { cardClass } from "./business-ui";
import { HomeHeading } from "./foundation/HomeHeading";
import { HOME_DEFAULT_ORDER, HomeCustomize, HomeWork, useHomeOrder, type HomeSectionKey } from "./inicio/HomeOverviewDraft";
import { SetupGuide } from "./inicio/SetupGuide";
import { useBusinessSetup } from "./inicio/useBusinessSetup";

/**
 * Inicio: the setup guide while setup is open, the greeting (in the top bar from the tablet up, here on a phone), then
 * its three layers in the person's order: Resumen del negocio, Finanzas por mes and Cobros y pagos. The month-close
 * panel loads once and hands over its month and money parts. Agregar lives in the top bar; a phone keeps its page button.
 */
export default function BusinessOverviewPanel() {
  const { isBelowTablet } = useResponsiveLayout();
  const { records, bridge, reload, chosen, userId } = useBusiness();
  const { t } = useTranslation();
  const waiting = inboxCount(records);
  const reading = readingCount(records) ?? 0;
  const monthClose = useMonthCloseSource();
  // Cobros y pagos is Por cobrar and Por pagar: no section, and nothing to reorder, while settlement is off.
  const shown = businessSettlementAvailable(records.workspace) ? HOME_DEFAULT_ORDER : HOME_DEFAULT_ORDER.filter((key) => key !== "money");
  const homeOrder = useHomeOrder(userId, chosen?.space_id, shown);
  // Asked here, outside the month panel's arrangement, so a re-arranged Inicio does not ask again.
  const setup = useBusinessSetup();

  const home = (parts: MonthCloseParts) => {
    const sections: Record<HomeSectionKey, React.ReactNode> = { work: <HomeWork />, month: parts.month, money: parts.money };
    return (
      <div data-testid="home-overview" className="w-full space-y-6 pb-6">
        <SetupGuide setup={setup} />
        {isBelowTablet ? <HomeHeading name={bridge?.greetingName} business={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} /> : null}
        {parts.receiptStatus ? <div className={cardClass}>{parts.receiptStatus}</div> : null}
        {homeOrder.order.map((key) => <div key={key} data-home-section={key}>{sections[key]}</div>)}
        <div className="flex border-t border-[color:var(--surface-divider)] pt-4"><HomeCustomize order={homeOrder.order} defaults={homeOrder.defaults} onChange={homeOrder.save} isDefault={homeOrder.isDefault} /></div>
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
        review={records.error ? (records.refused ? { state: "refused", reference: records.failureReference } : { state: "failed", retry: reload, reference: records.failureReference }) : waiting === null ? { state: records.inbox === null ? "loading" : "unknown" } : { count: waiting, reading }}
      />
    </section>
  );
}
