"use client";

import { useTheme } from "next-themes";
import { useTranslation } from "react-i18next";
import { useConversationSurface } from "@/components/chat/ChatWorkspace";
import { AppMiniature, PreviewChoice } from "@/components/settings/PreviewChoice";
import SettingsSurface from "@/components/settings/SettingsSurface";
import { Switch } from "@/components/ui/Switch";
import { setSwitchLabelsShown, useSwitchLabelsShown } from "@/lib/switch-labels";

type AppearanceModalProps = {
  onClose: () => void;
  /** Present when opened from a parent panel, so back returns rather than closes. */
  onBack?: () => void;
  backLabel?: string;
};

type Theme = "light" | "dark" | "system";

/**
 * Light, Dark or System, each shown as the app in miniature. The choice stays
 * in this browser; the account holds no theme. Business also keeps its
 * switch-words choice here, beside the look it changes.
 */
export default function AppearanceModal({
  onClose,
  onBack,
  backLabel,
}: AppearanceModalProps) {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const isBusiness = useConversationSurface() === "business";
  const switchLabelsShown = useSwitchLabelsShown();

  const current: Theme = theme === "light" || theme === "dark" || theme === "system" ? theme : "system";

  return (
    <SettingsSurface
      title={t("settings.app.appearance", "Appearance")}
      closeLabel={t("settings.app.close_appearance", "Close appearance")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="sm"
    >
      <div className="p-5">
        <PreviewChoice<Theme>
          testId="appearance-options"
          label={t("settings.app.appearance", "Appearance")}
          value={current}
          onChange={setTheme}
          options={[
            { key: "light", label: t("settings.app.appearance_options.light"), preview: <AppMiniature tone="light" /> },
            { key: "dark", label: t("settings.app.appearance_options.dark"), preview: <AppMiniature tone="dark" /> },
            {
              key: "system",
              label: t("settings.app.appearance_options.system"),
              preview: (
                <>
                  <AppMiniature tone="light" />
                  <span className="absolute inset-0 [clip-path:polygon(55%_0,100%_0,100%_100%,45%_100%)]">
                    <AppMiniature tone="dark" />
                  </span>
                </>
              ),
            },
          ]}
        />
        {isBusiness ? (
          <div className="mt-[21px] flex min-h-11 items-center justify-between gap-3 border-t border-[#DCE0DA] pt-[13px] text-[16px] text-black dark:border-white/10 dark:text-white">
            <span>{t("settings.app.switch_labels", "Words on switches")}</span>
            <Switch testId="settings-switch-labels" label={t("settings.app.switch_labels", "Words on switches")} checked={switchLabelsShown} onChange={setSwitchLabelsShown} />
          </div>
        ) : null}
      </div>
    </SettingsSurface>
  );
}
