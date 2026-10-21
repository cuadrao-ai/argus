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
import { getClosedBusinessSpaces, getOwnedBusinessSpaces } from "@/lib/business-lifecycle-api";
import BusinessLifecycleControls from "./BusinessLifecycleControls";
import BusinessLifecycleEntry from "./BusinessLifecycleEntry";
import BusinessTransferEntry from "./BusinessTransferEntry";
import { primaryButtonClass } from "./business-ui";

export default function BusinessApp({ sample, transferId, lifecycle, manageLifecycle }: { sample?: FixtureOptions; transferId?: string; lifecycle?: { action: "close" | "transfer"; spaceId: string }; manageLifecycle?: boolean }) {
  const { t } = useTranslation();
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  const [lifecycleHome, setLifecycleHome] = useState<"loading" | "workspace" | "closed" | "unavailable">(source.mode === "fixture" || lifecycle || transferId || manageLifecycle ? "workspace" : "loading");
  const [lifecycleActor, setLifecycleActor] = useState<string | null | undefined>(undefined);
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
  useEffect(() => {
    if (source.mode === "fixture" || lifecycle || transferId || manageLifecycle || (process.env.NEXT_PUBLIC_MOCK_AUTH !== "true" && !owner)) return;
    setLifecycleHome("loading");
    const controller = new AbortController();
    void Promise.all([getOwnedBusinessSpaces(controller.signal), getClosedBusinessSpaces(controller.signal)]).then(([open, closed]) => {
      if (!controller.signal.aborted) { setLifecycleActor(owner); setLifecycleHome(!open.length && closed.length ? "closed" : "workspace"); }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setLifecycleActor(owner); setLifecycleHome(((error as { code?: string }).code === "business_unavailable" || (error as { status?: number }).status === 404) ? "workspace" : "unavailable"); }
    });
    return () => controller.abort();
  }, [source, lifecycle, transferId, manageLifecycle, owner]);
  if (!sample && process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
    if (owner === undefined || (owner === null && isLeavingSession())) return null;
    if (owner === null) return <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-6 text-center">
      <p role="alert">{t("chat.account_changed")}</p>
      <button type="button" className={primaryButtonClass} onClick={() => window.location.assign("/?auth=login")}>{t("chat.account_changed_reload")}</button>
    </main>;
  }
  if (lifecycle) return <BusinessLifecycleEntry key={`${owner}/${lifecycle.action}/${lifecycle.spaceId}`} {...lifecycle} />;
  if (source.mode === "live" && !transferId && !manageLifecycle && lifecycleActor !== owner) return null;
  if (manageLifecycle || lifecycleHome === "closed") return <main className="mx-auto max-w-xl p-6"><h1 className="font-display text-xl">{t("business.overview.title", "My business")}</h1><BusinessLifecycleControls key={owner ?? "fixture"} /></main>;
  if (lifecycleHome === "loading") return null;
  if (lifecycleHome === "unavailable") return <p role="alert" className="p-6">{t("common.error_occurred")}</p>;
  const consentUserId = sample || process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? MOCK_AUTH_CONSENT_USER_ID : owner;
  const workspace = (
    <BusinessWorkspaceProvider key={owner ?? "fixture"} source={source}>
      <BusinessNamingProvider>
      <ConversationShellGuard />
      <ConversationUnavailableNotice />
      <ChatInterface />
      {!sample && transferId ? <BusinessTransferEntry transferId={transferId} /> : null}
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
