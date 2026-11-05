"use client";

import { useTheme } from "next-themes";
import { useTranslation } from "react-i18next";
import { AppMiniature, PreviewChoice } from "@/components/settings/PreviewChoice";
import SettingsSurface from "@/components/settings/SettingsSurface";

export type SidebarMode = "expanded" | "collapsed" | "hover";

type SidebarPreferenceModalProps = {
  mode: SidebarMode;
  business?: boolean;
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
  business = false,
  onSelect,
  onClose,
  onBack,
  backLabel,
}: SidebarPreferenceModalProps) {
  const { t } = useTranslation();
  const tone = useTheme().resolvedTheme === "light" ? "light" : "dark";

  // The rail changes beside the sheet as it is picked, so the sheet stays open.
  return (
    <SettingsSurface
      title={t("settings.sidebar.title")}
      closeLabel={t("settings.sidebar.close")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
    >
      <p className="px-5 pt-3 text-[14px] text-[#56635e] dark:text-white/70">
        {t("settings.sidebar.description")}
      </p>
      <div className="p-4">
        <PreviewChoice<SidebarMode>
          testId="sidebar-mode-options"
          label={t("settings.sidebar.title")}
          value={mode}
          onChange={onSelect}
          options={[
            { key: "expanded", label: t("settings.sidebar.expanded"), preview: <AppMiniature tone={tone} /> },
            { key: "collapsed", label: t("settings.sidebar.collapsed"), preview: <AppMiniature tone={tone} rail="icons" /> },
            ...(!business ? [{ key: "hover" as const, label: t("settings.sidebar.hover"), preview: <AppMiniature tone={tone} rail="icons" /> }] : []),
          ]}
        />
      </div>
    </SettingsSurface>
  );
}
