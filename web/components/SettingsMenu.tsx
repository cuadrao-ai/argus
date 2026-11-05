"use client";

import { useSyncExternalStore } from "react";
import { Monitor, Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";
import { useTranslation } from "react-i18next";

const subscribe = () => () => {};
const clientSnapshot = () => true;
const serverSnapshot = () => false;

export function SettingsMenu() {
  const { t } = useTranslation();
  const { theme, setTheme } = useTheme();
  const mounted = useSyncExternalStore(subscribe, clientSnapshot, serverSnapshot);
  const options = [
    { id: "system", label: t("settings.app.appearance_options.system"), icon: Monitor },
    { id: "light", label: t("settings.app.appearance_options.light"), icon: Sun },
    { id: "dark", label: t("settings.app.appearance_options.dark"), icon: Moon },
  ] as const;

  return (
    <div className="absolute right-6 top-6 z-40 tablet:right-12 tablet:top-8">
      <div
        role="group"
        aria-label={t("settings.app.appearance")}
        className="flex rounded-full border border-[#dce0da] p-1 dark:border-white/15"
      >
        {options.map(({ id, label, icon: Icon }) => {
          const selected = mounted && theme === id;
          return (
            <button
              key={id}
              type="button"
              aria-label={label}
              aria-pressed={selected}
              title={label}
              onClick={() => setTheme(id)}
              className={`flex h-11 w-11 items-center justify-center rounded-full transition-colors duration-150 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#2f5a49] dark:focus-visible:ring-[#8fcbb0] desktop:h-8 desktop:w-8 ${
                selected
                  ? "bg-black/[0.06] text-[#172b26] dark:bg-white/10 dark:text-[#fafbf8]"
                  : "text-[#56635e] hover:bg-black/[0.035] hover:text-[#172b26] dark:text-white/65 dark:hover:bg-white/5 dark:hover:text-[#fafbf8]"
              }`}
            >
              <Icon className="h-3.5 w-3.5" aria-hidden="true" />
            </button>
          );
        })}
      </div>
    </div>
  );
}
