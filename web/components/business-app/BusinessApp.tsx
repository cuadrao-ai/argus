"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { isLeavingSession } from "@/lib/logout-flow";
import { getSupabaseClient } from "@/lib/supabase-client";
import FullscreenLoading, { FullscreenLoadingBoundary } from "@/components/FullscreenLoading";
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
import { getBusinessDirectory, type ClosedGrantedSpace } from "@/lib/business-api";
import BusinessLifecycleControls, { BusinessClosedAccess } from "./BusinessLifecycleControls";
import BusinessLifecycleEntry from "./BusinessLifecycleEntry";
import BusinessTransferEntry from "./BusinessTransferEntry";
import { primaryButtonClass } from "./business-ui";

type BusinessAppProps = { sample?: FixtureOptions; transferId?: string; lifecycle?: { action: "close" | "transfer"; spaceId: string }; manageLifecycle?: boolean };

export default function BusinessApp(props: BusinessAppProps) {
  return <FullscreenLoadingBoundary><BusinessAppContent {...props} /></FullscreenLoadingBoundary>;
}

function BusinessAppContent({ sample, transferId, lifecycle, manageLifecycle }: BusinessAppProps) {
  const { t } = useTranslation();
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  const [lifecycleHome, setLifecycleHome] = useState<"loading" | "workspace" | "closed" | "member_closed" | "unavailable">(source.mode === "fixture" || lifecycle || transferId || manageLifecycle ? "workspace" : "loading");
  const [closedMemberships, setClosedMemberships] = useState<ClosedGrantedSpace[]>([]);
  const [attempt, setAttempt] = useState(0);
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
    void getBusinessDirectory(controller.signal).then(directory => {
      if (!controller.signal.aborted) {
        setClosedMemberships(directory.closed_spaces);
        setLifecycleActor(owner);
        setLifecycleHome(directory.spaces.length ? "workspace" : directory.closed_spaces.some(space => space.role === "owner") ? "closed" : directory.closed_spaces.length ? "member_closed" : "workspace");
      }
    }).catch((error: unknown) => {
      if (!controller.signal.aborted) { setLifecycleActor(owner); setLifecycleHome(((error as { code?: string }).code === "business_unavailable" || (error as { status?: number }).status === 404) ? "workspace" : "unavailable"); }
    });
    return () => controller.abort();
  }, [source, lifecycle, transferId, manageLifecycle, owner, attempt]);
  if (!sample && process.env.NEXT_PUBLIC_MOCK_AUTH !== "true") {
    if (owner === undefined) return <FullscreenLoading />;
    if (owner === null && isLeavingSession()) return null;
    if (owner === null) return <main className="flex h-[100dvh] flex-col items-center justify-center gap-4 p-6 text-center">
      <p role="alert">{t("chat.account_changed")}</p>
      <button type="button" className={primaryButtonClass} onClick={() => window.location.assign("/?auth=login")}>{t("chat.account_changed_reload")}</button>
    </main>;
  }
  if (lifecycle) return <BusinessLifecycleEntry key={`${owner}/${lifecycle.action}/${lifecycle.spaceId}`} {...lifecycle} />;
  if (source.mode === "live" && !transferId && !manageLifecycle && lifecycleActor !== owner) return <FullscreenLoading />;
  if (lifecycleHome === "member_closed") return <BusinessClosedAccess returnHome businessName={closedMemberships[0].name} onReturn={() => window.location.assign("/")} />;
  if (manageLifecycle || lifecycleHome === "closed") return <main className="mx-auto max-w-xl p-6"><h1 className="font-display text-xl">{t("business.overview.title", "My business")}</h1><BusinessLifecycleControls key={owner ?? "fixture"} /></main>;
  if (lifecycleHome === "loading") return <FullscreenLoading />;
  if (lifecycleHome === "unavailable") return <main className="space-y-4 p-6"><p role="alert">{t("business.lifecycle.errors.discovery")}</p><button type="button" className={primaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></main>;
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
