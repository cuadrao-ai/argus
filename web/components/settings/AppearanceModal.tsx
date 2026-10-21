"use client";

import { useTheme } from "next-themes";
import { Sun, Moon, Monitor } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { SegmentedControl } from "@/components/ui/SegmentedControl";

type AppearanceModalProps = {
  onClose: () => void;
  /** Present when opened from a parent panel, so back returns rather than closes. */
  onBack?: () => void;
  backLabel?: string;
};

/**
 * Segmented Light / Dark / System. The choice stays in this browser; the
 * account holds no theme. The shell decides sheet or dialog.
 */
export default function AppearanceModal({
  onClose,
  onBack,
  backLabel,
}: AppearanceModalProps) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();

  const current = theme === "light" || theme === "dark" || theme === "system" ? theme : "system";

  // The theme changes behind the sheet as it is picked, so the sheet stays open to compare.
  return (
    <AdaptivePanel
      title={t("settings.app.appearance", "Appearance")}
      closeLabel={t("settings.app.close_appearance", "Close appearance")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
    >
      <div className="p-4">
        <SegmentedControl
          fill
          testId="appearance-options"
          label={t("settings.app.appearance", "Appearance")}
          value={current}
          onChange={setTheme}
          segments={[
            { key: "light", label: t("settings.app.appearance_options.light"), icon: Sun },
            { key: "dark", label: t("settings.app.appearance_options.dark"), icon: Moon },
            { key: "system", label: t("settings.app.appearance_options.system"), icon: Monitor },
          ]}
        />
      </div>
    </AdaptivePanel>
  );
}
