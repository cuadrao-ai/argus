"use client";

import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness, type BusinessTab } from "./BusinessWorkspace";
import BusinessLifecycleControls from "./BusinessLifecycleControls";
import BusinessProfilePreview from "@/app/design-workspace/BusinessProfilePreview";
import BusinessAccessPreview from "@/app/design-workspace/BusinessAccessPreview";
import BusinessReception from "./BusinessReception";
import { formatBusinessName } from "./business-format";
import { PanelHeading } from "./business-ui";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BusinessAddMenu from "./BusinessAddMenu";

export default function BusinessSettingsPanel({ tab = "datos" }: { tab?: BusinessTab }) {
  const { t } = useTranslation();
  const { chosen, openPanel, source } = useBusiness();
  const { isBelowTablet } = useResponsiveLayout();
  const owner = chosen?.role === "owner";
  const manager = source.mode === "live" ? chosen?.permissions?.includes("manage") : owner;
  const tabs = [
    { key: "datos" as const, label: t("business.settings.tab_datos", "Details") },
    ...(manager ? [{ key: "equipo" as const, label: t("business.settings.tab_equipo", "Access") }] : []),
    { key: "correo" as const, label: isBelowTablet ? t("business.settings.tab_correo_short", "Reception") : t("business.settings.tab_correo", "Reception") },
  ];
  const shown = tabs.some((item) => item.key === tab) ? tab : "datos";
  return (
    <section data-testid="business-settings">
      <PanelHeading title={t("business.settings.title", "Business")} subtitle={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} action={isBelowTablet ? undefined : <BusinessAddMenu placement="header" />} />
      <div className="mb-6">
        <SegmentedControl testId="business-settings-tabs" label={t("business.settings.title", "Business")} value={shown} onChange={(next) => openPanel({ kind: "business", tab: next })} segments={tabs} fill={isBelowTablet} />
      </div>
      {shown === "datos" ? (
        <div className="space-y-6">
          <BusinessProfilePreview key={chosen?.space_id} />
          {owner && source.mode === "live" ? <BusinessLifecycleControls spaceId={chosen?.space_id} /> : null}
        </div>
      ) : null}
      {shown === "equipo" ? <BusinessAccessPreview key={chosen?.space_id} /> : null}
      {shown === "correo" ? <BusinessReception key={chosen?.space_id} /> : null}
    </section>
  );
}
