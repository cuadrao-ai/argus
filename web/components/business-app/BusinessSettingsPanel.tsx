"use client";

import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness, type BusinessTab } from "./BusinessWorkspace";
import BusinessAccessPanel from "./BusinessAccessPanel";
import BusinessFiscalProfile from "./BusinessFiscalProfile";
import { BusinessEmailAddress, EmailHistory } from "./BusinessEmailDeliveries";
import { formatBusinessName } from "./business-format";
import { PanelHeading } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";

/**
 * Negocio: everything about the business itself, apart from the person's own
 * account (which lives at the top right). One page, three tabs: its name and
 * RNC, who has access, and the address that receives its receipts by email
 * with the history of every email that arrived under it.
 */
export default function BusinessSettingsPanel({ tab = "datos" }: { tab?: BusinessTab }) {
  const { t } = useTranslation();
  const { chosen, openPanel } = useBusiness();
  const { isBelowTablet } = useResponsiveLayout();
  const owner = chosen?.role !== "accountant";
  const tabs = [
    { key: "datos" as const, label: t("business.settings.tab_datos", "Details") },
    ...(owner ? [{ key: "equipo" as const, label: isBelowTablet ? t("business.settings.tab_equipo_short", "Team") : t("business.settings.tab_equipo", "Team and access") }] : []),
    { key: "correo" as const, label: isBelowTablet ? t("business.settings.tab_correo_short", "Email") : t("business.settings.tab_correo", "Receipt email") },
  ];
  const shown = tabs.some((item) => item.key === tab) ? tab : "datos";
  return (
    <section data-testid="business-settings">
      <PanelHeading title={t("business.settings.title", "Business")} subtitle={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} />
      <div className="mb-6">
        <SegmentedControl testId="business-settings-tabs" label={t("business.settings.title", "Business")} value={shown} onChange={(next) => openPanel({ kind: "business", tab: next })} segments={tabs} fill={isBelowTablet} />
      </div>
      {shown === "datos" ? (
        <div className={SURFACE_CARD}>
          <h2 className="font-display text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.settings.datos_title", "Name and RNC")}</h2>
          <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.settings.datos_body", "They appear on your 606 and 607 and on what you export.")}</p>
          <BusinessFiscalProfile />
        </div>
      ) : null}
      {shown === "equipo" ? <BusinessAccessPanel embedded /> : null}
      {shown === "correo" ? (
        <div className="space-y-6">
          <div className={SURFACE_CARD}><BusinessEmailAddress /></div>
          <EmailHistory />
        </div>
      ) : null}
    </section>
  );
}
