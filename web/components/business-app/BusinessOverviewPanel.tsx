"use client";

import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { formatBusinessName } from "./business-format";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import BusinessMonthClosePanel, { useMonthCloseSource, type MonthCloseParts } from "./BusinessMonthClosePanel";
import { HomeHeading } from "./foundation/HomeHeading";
import { HomeAttention } from "./inicio/HomeAttention";

/**
 * Inicio: the greeting (in the top bar from the tablet up, here on a phone), then two cards side by side: what needs
 * attention on the left, flexible, and the month on the right at a fixed 440px. A phone stacks them in that order.
 * Cobros y pagos follows only while settlement is on. Agregar lives in the top bar; a phone keeps its page button.
 */
export default function BusinessOverviewPanel() {
  const { isBelowTablet } = useResponsiveLayout();
  const { bridge, chosen } = useBusiness();
  const { t } = useTranslation();
  const monthClose = useMonthCloseSource();

  const home = (parts: MonthCloseParts) => (
    <div data-testid="home-overview" className="w-full space-y-6 pb-6">
      {isBelowTablet ? <HomeHeading name={bridge?.greetingName} business={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} /> : null}
      <div className="@container">
        <div data-testid="home-columns" className="flex flex-col gap-6 @min-[56rem]:grid @min-[56rem]:grid-cols-[minmax(0,1fr)_440px] @min-[56rem]:items-start">
          <HomeAttention firstDay={parts.firstDay} />
          {parts.month}
        </div>
      </div>
      {parts.money}
    </div>
  );

  return (
    <section aria-labelledby="business-overview-title">
      {isBelowTablet ? <div data-testid="inicio-actions" className="mb-5 empty:hidden" style={{ paddingTop: 32 }}><BusinessAddMenu placement="page" /></div> : null}
      <BusinessMonthClosePanel monthClose={monthClose} layout="finance" arrange={home} />
    </section>
  );
}
