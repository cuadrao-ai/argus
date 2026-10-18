"use client";

import { useMemo, useState, type ReactNode } from "react";
import { BusinessConsentContext } from "./business-consent-context";
import {
  BusinessConsentAccepted,
  BusinessConsentDeclined,
  BusinessConsentHeld,
  BusinessConsentScreen,
} from "./BusinessConsentScreen";
import { acceptanceMatchesCurrentNotice } from "@/lib/business-privacy-notice";
import {
  createStubPrivacyNoticeClient,
  readPrivacyNoticeAcceptance,
} from "@/lib/business-privacy-notice-client";

type Phase = "screen" | "declined" | "saved" | "app";

/**
 * Shows the notice before model features, and keeps those features unreachable
 * until this person has accepted the current version. Declining explains the
 * consequence and leaves manual recording available.
 */
export default function BusinessConsentGate({ userId, children }: { userId: string; children: ReactNode }) {
  const client = useMemo(() => createStubPrivacyNoticeClient(), []);
  const initiallyAccepted = acceptanceMatchesCurrentNotice(readPrivacyNoticeAcceptance(userId), userId);
  const [phase, setPhase] = useState<Phase>(initiallyAccepted ? "app" : "screen");
  const [accepted, setAccepted] = useState(initiallyAccepted);
  const value = useMemo(
    () => ({ accepted: phase === "app" && accepted, reopen: () => setPhase("screen") }),
    [accepted, phase],
  );

  return (
    <BusinessConsentContext.Provider value={value}>
      {phase === "screen" ? (
        <BusinessConsentScreen
          userId={userId}
          client={client}
          onAccepted={() => {
            setAccepted(true);
            setPhase("saved");
          }}
          onDecline={() => setPhase("declined")}
        />
      ) : null}
      {phase === "declined" ? (
        <BusinessConsentDeclined
          onBack={() => setPhase("screen")}
          onContinue={() => {
            setAccepted(false);
            setPhase("app");
          }}
        />
      ) : null}
      {phase === "saved" ? <BusinessConsentAccepted onContinue={() => setPhase("app")} /> : null}
      {phase === "app" ? (
        <>
          {accepted ? null : <BusinessConsentHeld onReview={() => setPhase("screen")} />}
          {children}
        </>
      ) : null}
    </BusinessConsentContext.Provider>
  );
}
