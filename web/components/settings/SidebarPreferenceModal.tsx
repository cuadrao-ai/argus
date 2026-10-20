"use client";

import { Layout, LayoutPanelLeft, MousePointer2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { SegmentedControl } from "@/components/ui/SegmentedControl";

export type SidebarMode = "expanded" | "collapsed" | "hover";

type SidebarPreferenceModalProps = {
  mode: SidebarMode;
  onSelect: (mode: SidebarMode) => void;
  onClose: () => void;
  onBack?: () => void;
  backLabel?: string;
};

/**
 * The sidebar preference: Expanded, Collapsed or Expand on Hover.
 */
export default function SidebarPreferenceModal({
  mode,
  onSelect,
  onClose,
  onBack,
  backLabel,
}: SidebarPreferenceModalProps) {
  const { t } = useTranslation();

  // The rail changes beside the sheet as it is picked, so the sheet stays open.
  return (
    <AdaptivePanel
      title={t("settings.sidebar.title")}
      closeLabel={t("settings.sidebar.close")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
    >
      <p className="px-5 pt-3 text-[13px] text-[#56635e] dark:text-white/70">
        {t("settings.sidebar.description")}
      </p>
      <div className="p-4">
        <SegmentedControl
          fill
          stacked
          testId="sidebar-mode-options"
          label={t("settings.sidebar.title")}
          value={mode}
          onChange={onSelect}
          segments={[
            { key: "expanded", label: t("settings.sidebar.expanded"), icon: Layout },
            { key: "collapsed", label: t("settings.sidebar.collapsed"), icon: LayoutPanelLeft },
            { key: "hover", label: t("settings.sidebar.hover"), icon: MousePointer2 },
          ]}
        />
      </div>
    </AdaptivePanel>
  );
}
