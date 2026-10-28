"use client";

import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useBusiness, type BusinessTab } from "./BusinessWorkspace";
import { canManageBusiness } from "./business-ui";
import BusinessLifecycleControls from "./BusinessLifecycleControls";
import BusinessProfilePreview from "@/app/design-workspace/BusinessProfilePreview";
import BusinessAccessPreview from "@/app/design-workspace/BusinessAccessPreview";
import BusinessReception from "./BusinessReception";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { PageHeading } from "./foundation/PageHeading";
import { SettingsColumns, SettingsLayout } from "./foundation/SettingsLayout";

export default function BusinessSettingsPanel({ tab = "datos" }: { tab?: BusinessTab }) {
  const { t } = useTranslation();
  const { chosen, openPanel, source } = useBusiness();
  const { isBelowTablet } = useResponsiveLayout();
  const owner = chosen?.role === "owner";
  const manager = canManageBusiness(chosen, source.mode === "live");
  const tabs = [
    { key: "datos" as const, label: t("business.settings.tab_datos", "Details") },
    ...(manager ? [{ key: "equipo" as const, label: t("business.settings.tab_equipo", "Access") }] : []),
    { key: "correo" as const, label: isBelowTablet ? t("business.settings.tab_correo_short", "Reception") : t("business.settings.tab_correo", "Reception") },
  ];
  const shown = tabs.some((item) => item.key === tab) ? tab : "datos";
  return (
    <section data-testid="business-settings">
      {/* Same heading group as the main screens; adding documents is not a Negocio task, so no Agregar here. */}
      <PageHeading screen="business" />
      <SettingsLayout tabs={<SegmentedControl testId="business-settings-tabs" label={t("business.settings.title", "Business")} value={shown} onChange={(next) => openPanel({ kind: "business", tab: next })} segments={tabs} fill={isBelowTablet} />}>
        {shown === "datos" ? (
          <div className="space-y-6">
            <BusinessProfilePreview key={chosen?.space_id} />
            {owner && source.mode === "live" ? <SettingsColumns main={<BusinessLifecycleControls spaceId={chosen?.space_id} />} /> : null}
          </div>
        ) : null}
        {shown === "equipo" ? <SettingsColumns main={<BusinessAccessPreview key={chosen?.space_id} />} /> : null}
        {shown === "correo" ? <SettingsColumns main={<BusinessReception key={chosen?.space_id} />} /> : null}
      </SettingsLayout>
    </section>
  );
}
