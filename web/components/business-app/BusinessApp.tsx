"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { isLeavingSession } from "@/lib/logout-flow";
import { getSupabaseClient } from "@/lib/supabase-client";
import ChatInterface from "@/components/chat/ChatInterface";
import ConversationShellGuard from "@/components/chat/ConversationShellGuard";
import BusinessNamingProvider from "./BusinessNamingProvider";
import ConversationUnavailableNotice from "./ConversationUnavailableNotice";
import BusinessConsentGate from "./BusinessConsentGate";
import { BusinessConsentTestProvider } from "./business-consent-context";
import { MOCK_AUTH_CONSENT_USER_ID } from "@/lib/business-privacy-notice";
import { BusinessWorkspaceProvider } from "./BusinessWorkspace";
import { liveBusinessDataSource, type BusinessDataSource } from "./business-data";
import { createFixtureBusinessDataSource, type FixtureOptions } from "./fixture-data";
import { primaryButtonClass } from "./business-ui";

export default function BusinessApp({ sample }: { sample?: FixtureOptions }) {
  const { t } = useTranslation();
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  const [owner, setOwner] = useState<string | null | undefined>(undefined);
  useEffect(() => {
    const root = document.documentElement;
    const previous = root.lang;
    root.lang = "es";
    return () => { root.lang = previous; };
  }, []);
  useEffect(() => {
    if (sample || process.env.NEXT_PUBLIC_MOCK_AUTH === "true") return;
    const client = getSupabaseClient();
    if (!client) return;
    let active = true;
    let observed = false;
    const { data } = client.auth.onAuthStateChange((_event, session) => {
      observed = true;
      if (active) setOwner(session?.user.id ?? null);
    });
    void client.auth.getSession().then(({ data, error }) => {
      if (active && !observed && !error) setOwner(data.session?.user.id ?? null);
    }).catch(() => undefined);
    return () => { active = false; data.subscription.unsubscribe(); };
  }, [sample]);
  if (!sample && process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
    if (owner === undefined || (owner === null && isLeavingSession())) return null;
    if (owner === null) return <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-6 text-center">
      <p role="alert">{t("chat.account_changed")}</p>
      <button type="button" className={primaryButtonClass} onClick={() => window.location.assign("/?auth=login")}>{t("chat.account_changed_reload")}</button>
    </main>;
  }
  const consentUserId = sample || process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? MOCK_AUTH_CONSENT_USER_ID : owner;
  const workspace = (
    <BusinessWorkspaceProvider key={owner ?? "fixture"} source={source}>
      <BusinessNamingProvider>
      <ConversationShellGuard />
      <ConversationUnavailableNotice />
      <ChatInterface />
      </BusinessNamingProvider>
    </BusinessWorkspaceProvider>
  );
  if (sample) return <BusinessConsentTestProvider accepted>{workspace}</BusinessConsentTestProvider>;
  if (!consentUserId) return workspace;
  return (
    <BusinessConsentGate key={consentUserId} source={source}>
      {workspace}
    </BusinessConsentGate>
  );
}
