"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import {
  BUSINESS_PRIVACY_NOTICE_VERSION,
  acceptanceMatchesCurrentNotice,
  currentNoticeHashes,
  isPrivacyNoticeLocale,
  type PrivacyNoticeLocale,
} from "@/lib/business-privacy-notice";
import {
  createStubPrivacyNoticeClient,
  readPrivacyNoticeAcceptance,
  revokeEnabledReceiptReading,
} from "@/lib/business-privacy-notice-client";
import type { BusinessDataSource } from "./business-data";
import { BusinessConsentContext } from "./business-consent-context";
import {
  BusinessConsentAccepted,
  BusinessConsentDeclined,
  BusinessConsentHeld,
  BusinessConsentScreen,
} from "./BusinessConsentScreen";

type Phase = "checking" | "screen" | "declined" | "saved" | "app";

function storedNoticeIsPlausible(userId: string): boolean {
  const record = readPrivacyNoticeAcceptance(userId);
  return Boolean(
    record
    && record.userId === userId
    && record.noticeVersion === BUSINESS_PRIVACY_NOTICE_VERSION
    && record.acceptedAt.length > 0
    && isPrivacyNoticeLocale(record.locale),
  );
}

export default function BusinessConsentGate({
  userId,
  source,
  children,
}: {
  userId: string;
  source: Pick<BusinessDataSource, "receiptReading" | "setReceiptReading">;
  children: ReactNode;
}) {
  const { i18n } = useTranslation();
  const locale = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language) as PrivacyNoticeLocale;
  const client = useMemo(() => createStubPrivacyNoticeClient(), []);
  const [phase, setPhase] = useState<Phase>(() => (storedNoticeIsPlausible(userId) ? "checking" : "screen"));
  const [accepted, setAccepted] = useState(false);
  const [holding, setHolding] = useState(false);
  const [holdFailed, setHoldFailed] = useState(false);
  const value = useMemo(
    () => ({ accepted: phase === "app" && accepted, reopen: () => setPhase("screen") }),
    [accepted, phase],
  );

  useEffect(() => {
    let live = true;
    if (!storedNoticeIsPlausible(userId)) {
      setAccepted(false);
      setPhase("screen");
      return () => { live = false; };
    }
    setPhase("checking");
    void currentNoticeHashes().then((hashes) => {
      if (!live) return;
      const matches = acceptanceMatchesCurrentNotice(readPrivacyNoticeAcceptance(userId), userId, hashes);
      setAccepted(matches);
      setPhase(matches ? "app" : "screen");
    });
    return () => { live = false; };
  }, [userId]);

  const continueWithout = () => {
    setHolding(true);
    setHoldFailed(false);
    void revokeEnabledReceiptReading(source, locale)
      .then(() => {
        setAccepted(false);
        setPhase("app");
      })
      .catch(() => setHoldFailed(true))
      .finally(() => setHolding(false));
  };

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
          holding={holding}
          failed={holdFailed}
          onBack={() => setPhase("screen")}
          onContinue={continueWithout}
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
