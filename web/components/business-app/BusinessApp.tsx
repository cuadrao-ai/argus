"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { isLeavingSession } from "@/lib/logout-flow";
import { getSupabaseClient } from "@/lib/supabase-client";
import { synchronizeBusinessAccount } from "@/lib/business-grant";
import { createSessionRecovery, type SessionRecoveryState } from "@/lib/session-recovery";
import FullscreenLoading, { FullscreenLoadingBoundary } from "@/components/FullscreenLoading";
import { SessionRecoveryScreen } from "@/components/status/SessionRecoveryScreen";
import { SessionRecoveryContext, useSessionRecoveryState } from "@/components/status/session-recovery-context";
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
import { formatBusinessName } from "./business-format";

type BusinessAppProps = { sample?: FixtureOptions; transferId?: string; lifecycle?: { action: "close" | "transfer"; spaceId: string }; manageLifecycle?: boolean };
type LifecycleHome = "workspace" | "closed" | "member_closed" | "unavailable";
type DirectoryState = { scope: SessionRecoveryState; attempt: number; home: LifecycleHome; closed: ClosedGrantedSpace[] };

async function verifyBusinessAccess(userId: string, signal: AbortSignal): Promise<"allowed" | "missing" | "error"> {
  const identity = await getSupabaseClient()?.auth.getUser();
  if (!identity || identity.error) return "error";
  if (!identity.data.user) return "missing";
  if (identity.data.user.id !== userId || identity.data.user.is_anonymous) return "error";
  signal.throwIfAborted();
  await getBusinessDirectory(signal, userId);
  return "allowed";
}

export default function BusinessApp(props: BusinessAppProps) {
  return <FullscreenLoadingBoundary><BusinessAppContent {...props} /></FullscreenLoadingBoundary>;
}

function BusinessAppContent({ sample, transferId, lifecycle, manageLifecycle }: BusinessAppProps) {
  const { t } = useTranslation();
  const [source] = useState<BusinessDataSource>(() =>
    sample ? createFixtureBusinessDataSource(sample) : liveBusinessDataSource,
  );
  const [recovery] = useState(() => createSessionRecovery({ onIdentityChange: synchronizeBusinessAccount, verifyAccess: verifyBusinessAccess }));
  const checkSession = !sample && process.env.NEXT_PUBLIC_MOCK_AUTH !== "true";
  const session = useSessionRecoveryState(recovery, checkSession);
  const owner = session.kind === "same-owner" ? session.userId : undefined;
  const scopeKey = session.kind === "same-owner" ? `${session.userId}/${session.scope}` : "fixture";
  const discoverDirectory = source.mode === "live" && !lifecycle && !transferId && !manageLifecycle;
  const [directory, setDirectory] = useState<DirectoryState | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!discoverDirectory || (checkSession && !owner)) return;
    const controller = new AbortController();
    const stop = recovery.onRetire(() => { controller.abort(); setDirectory(null); });
    const current = () => !controller.signal.aborted && recovery.getSnapshot() === session;
    void getBusinessDirectory(controller.signal, owner).then(({ spaces, closed_spaces: closed }) => {
      const home = spaces.length ? "workspace" : closed.some(space => space.role === "owner") ? "closed" : closed.length ? "member_closed" : "workspace";
      if (current()) setDirectory({ scope: session, attempt, home, closed });
    }).catch((error: unknown) => {
      const problem = error as { code?: string; status?: number } | null;
      const home = problem?.code === "business_unavailable" || problem?.status === 404 ? "workspace" : "unavailable";
      if (current()) setDirectory({ scope: session, attempt, home, closed: [] });
    });
    return () => { stop(); controller.abort(); };
  }, [discoverDirectory, checkSession, recovery, session, owner, attempt]);
  if (checkSession && session.kind !== "same-owner") {
    if (session.kind === "pending") return <FullscreenLoading />;
    if (isLeavingSession()) return null;
    return <SessionRecoveryScreen state={session.kind} busy={session.busy} onRetry={recovery.retry} continueDisabled={session.kind === "different-owner" && !session.canContinue} onContinue={() => recovery.continueTo(() => window.location.replace("/biz"))} />;
  }
  if (lifecycle) return <BusinessLifecycleEntry key={`${scopeKey}/${lifecycle.action}/${lifecycle.spaceId}`} {...lifecycle} />;
  const currentDirectory = directory?.scope === session && directory.attempt === attempt ? directory : null;
  const lifecycleHome = discoverDirectory ? currentDirectory?.home ?? "loading" : "workspace";
  if (currentDirectory?.home === "member_closed") return <BusinessClosedAccess returnHome businessName={formatBusinessName(currentDirectory.closed[0].name, t("business.overview.title", "My business"))} onReturn={() => window.location.assign("/")} />;
  if (manageLifecycle || lifecycleHome === "closed") return <main className="mx-auto max-w-xl p-6"><h1 className="font-display text-xl">{t("business.overview.title", "My business")}</h1><BusinessLifecycleControls key={scopeKey} /></main>;
  if (lifecycleHome === "loading") return <FullscreenLoading />;
  if (lifecycleHome === "unavailable") return <main className="space-y-4 p-6"><p role="alert">{t("business.lifecycle.errors.discovery")}</p><button type="button" className={primaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></main>;
  const consentUserId = sample || process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? MOCK_AUTH_CONSENT_USER_ID : owner;
  const workspace = (
    <SessionRecoveryContext.Provider value={recovery}>
      <BusinessWorkspaceProvider key={scopeKey} userId={process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? MOCK_AUTH_CONSENT_USER_ID : owner ?? null} source={source}>
        <BusinessNamingProvider>
          <ConversationShellGuard />
          <ConversationUnavailableNotice />
          <ChatInterface />
          {!sample && transferId ? <BusinessTransferEntry transferId={transferId} /> : null}
        </BusinessNamingProvider>
      </BusinessWorkspaceProvider>
    </SessionRecoveryContext.Provider>
  );
  if (sample) return <BusinessConsentTestProvider accepted>{workspace}</BusinessConsentTestProvider>;
  if (!consentUserId) return workspace;
  return (
    <BusinessConsentGate key={scopeKey} source={source}>
      {workspace}
    </BusinessConsentGate>
  );
}
