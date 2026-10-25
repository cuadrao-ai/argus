"use client";

import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness, type BusinessTab } from "./BusinessWorkspace";
import BusinessLifecycleControls from "./BusinessLifecycleControls";
import BusinessAccessPanel from "./BusinessAccessPanel";
import BusinessProfilePreview from "@/app/design-workspace/BusinessProfilePreview";
import BusinessAccessPreview from "@/app/design-workspace/BusinessAccessPreview";
import BusinessFiscalProfile from "./BusinessFiscalProfile";
import BusinessReception from "./BusinessReception";
import { formatBusinessName } from "./business-format";
import { PanelHeading } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BusinessAddMenu from "./BusinessAddMenu";

export default function BusinessSettingsPanel({ tab = "datos" }: { tab?: BusinessTab }) {
  const { t } = useTranslation();
  const { chosen, openPanel, source } = useBusiness();
  const { isBelowTablet } = useResponsiveLayout();
  const owner = chosen?.role === "owner";
  const localPreview = process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true";
  const tabs = [
    { key: "datos" as const, label: t("business.settings.tab_datos", "Details") },
    ...(owner ? [{ key: "equipo" as const, label: t("business.settings.tab_equipo", "Access") }] : []),
    { key: "correo" as const, label: isBelowTablet ? t("business.settings.tab_correo_short", "Reception") : t("business.settings.tab_correo", "Reception") },
  ];
  const shown = tabs.some((item) => item.key === tab) ? tab : "datos";
  return (
    <section data-testid="business-settings">
      <PanelHeading title={t("business.settings.title", "Business")} subtitle={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} action={isBelowTablet ? undefined : <BusinessAddMenu placement="header" />} />
      <div className="mb-6">
        <SegmentedControl testId="business-settings-tabs" label={t("business.settings.title", "Business")} value={shown} onChange={(next) => openPanel({ kind: "business", tab: next })} segments={tabs} fill={isBelowTablet} />
      </div>
      {shown === "datos" ? localPreview ? <BusinessProfilePreview key={chosen?.space_id} /> : (
        <div className="space-y-6">
          <div className={SURFACE_CARD}>
            <h2 className="font-display text-[16px] font-medium text-[#172b26] dark:text-white">{t("business.settings.datos_title", "Name and RNC")}</h2>
            <p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("business.settings.datos_body", "They appear on your 606 and 607 and on what you export.")}</p>
            <BusinessFiscalProfile />
          </div>
          {owner && source.mode === "live" ? <BusinessLifecycleControls spaceId={chosen?.space_id} /> : null}
        </div>
      ) : null}
      {shown === "equipo" ? localPreview ? <BusinessAccessPreview key={chosen?.space_id} /> : <BusinessAccessPanel embedded /> : null}
      {shown === "correo" ? <BusinessReception key={chosen?.space_id} /> : null}
    </section>
  );
}
