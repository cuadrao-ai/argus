"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { getSupabaseClient } from "@/lib/supabase-client";
import ChatInterface from "@/components/chat/ChatInterface";
import ConversationShellGuard from "@/components/chat/ConversationShellGuard";
import BusinessNamingProvider from "./BusinessNamingProvider";
import ConversationUnavailableNotice from "./ConversationUnavailableNotice";
import { BusinessWorkspaceProvider } from "./BusinessWorkspace";
import { liveBusinessDataSource, type BusinessDataSource } from "./business-data";
import { createFixtureBusinessDataSource, type FixtureOptions } from "./fixture-data";

export default function BusinessApp({ sample }: { sample?: FixtureOptions }) {
  const { t } = useTranslation();
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  const [owner, setOwner] = useState<string | null | undefined>(undefined);
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
    if (owner === undefined) return null;
    if (owner === null) return <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-6 text-center">
      <p role="alert">{t("chat.account_changed")}</p>
      <button type="button" className="min-h-11 rounded-full px-6 py-3" onClick={() => window.location.assign("/?auth=login")}>{t("chat.account_changed_reload")}</button>
    </main>;
  }
  return (
    <BusinessWorkspaceProvider key={owner ?? "fixture"} source={source}>
      <BusinessNamingProvider>
      <ConversationShellGuard />
      <ConversationUnavailableNotice />
      <ChatInterface />
      </BusinessNamingProvider>
    </BusinessWorkspaceProvider>
  );
}
