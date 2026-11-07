"use client";

import i18next from "i18next";
import { useEffect, useLayoutEffect, useState } from "react";
import { I18nextProvider } from "react-i18next";

import { BusinessClosedNotice } from "@/components/status/BusinessClosedNotice";
import { OfflineBanner } from "@/components/status/OfflineBanner";
import { RemovedMemberScreen } from "@/components/status/RemovedMemberScreen";
import { ServerErrorScreen } from "@/components/status/ServerErrorScreen";
import { SessionRecoveryScreen } from "@/components/status/SessionRecoveryScreen";
import english from "@/public/locales/en/common.json";
import spanish from "@/public/locales/es-419/common.json";

function SessionRecoveryPreview({
  screen,
  language,
  theme,
}: {
  screen: "session-missing" | "session-error" | "session-changed" | "session-busy";
  language?: "en" | "es-419";
  theme?: "light" | "dark";
}) {
  const [retrying, setRetrying] = useState(false);
  const [previewI18n] = useState(() => {
    if (!language) return undefined;
    const instance = i18next.createInstance();
    void instance.init({
      lng: language,
      initAsync: false,
      resources: { en: { translation: english }, "es-419": { translation: spanish } },
      interpolation: { escapeValue: false },
    });
    return instance;
  });

  useLayoutEffect(() => {
    const html = document.documentElement;
    const originalDark = html.classList.contains("dark");
    const originalLanguage = html.lang;
    if (theme) html.classList.toggle("dark", theme === "dark");
    if (language) html.lang = language;
    return () => {
      if (theme) html.classList.toggle("dark", originalDark);
      if (language) html.lang = originalLanguage;
    };
  }, [language, theme]);

  useEffect(() => {
    if (!retrying) return;
    const timer = window.setTimeout(() => setRetrying(false), 1200);
    return () => window.clearTimeout(timer);
  }, [retrying]);

  const state = screen === "session-missing" ? "missing" : screen === "session-changed" ? "different-owner" : "error";
  const recovery = (
    <SessionRecoveryScreen
      state={state}
      busy={screen === "session-busy" || retrying}
      onRetry={() => setRetrying(true)}
      onContinue={() => undefined}
    />
  );
  return previewI18n ? <I18nextProvider i18n={previewI18n}>{recovery}</I18nextProvider> : recovery;
}

export default function ErrorScreenPreview({ screen, language, theme }: { screen: string; language?: string; theme?: string }) {
  if (screen === "session-missing" || screen === "session-error" || screen === "session-changed" || screen === "session-busy") {
    return (
      <SessionRecoveryPreview
        key={`${screen}/${language}/${theme}`}
        screen={screen}
        language={language === "en" || language === "es-419" ? language : undefined}
        theme={theme === "light" || theme === "dark" ? theme : undefined}
      />
    );
  }
  if (screen === "removed") return <RemovedMemberScreen onReturn={() => undefined} />;
  if (screen === "offline") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-[#F7F5EE] p-6">
        <div className="w-full max-w-md">
          <p className="mb-3 font-sans text-sm text-[#2f5a49]">factura.pdf</p>
          <OfflineBanner onRetry={() => undefined} />
        </div>
      </main>
    );
  }
  if (screen === "closed") {
    return (
      <main className="flex min-h-dvh items-center justify-center bg-[#fafbf8] p-6">
        <BusinessClosedNotice />
      </main>
    );
  }
  return <ServerErrorScreen onRetry={() => undefined} reference="c0ffee00" homeHref="/?auth=login" />;
}
