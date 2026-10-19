"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { getChosenGrant, grantNotLive, setChosenGrant } from "@/lib/business-grant";
import { consentCopyVersion } from "@/lib/business-privacy-notice";
import { normalizeEnabledLanguage, type ArgusLanguage } from "@/lib/language-features";
import type { BusinessDataSource } from "./business-data";
import { BusinessConsentContext } from "./business-consent-context";
import { BusinessConsentLoading, BusinessConsentScreen } from "./BusinessConsentScreen";

type Phase = "checking" | "screen" | "saving" | "app";

type ConsentSource = Pick<BusinessDataSource, "consent" | "acceptConsent" | "ensureSpace">;

/**
 * Saved in the Business the person works in: the chosen client's, else their
 * own, started first. A grant that died since it was chosen is dropped, and
 * the person's own Business takes it.
 */
async function acceptWhereWorking(source: ConsentSource, language: ArgusLanguage, version: string) {
  try {
    if (!getChosenGrant()) await source.ensureSpace(language);
    return await source.acceptConsent(version);
  } catch (error) {
    if (!grantNotLive(error) || !getChosenGrant()) throw error;
    setChosenGrant(null);
    await source.ensureSpace(language);
    return source.acceptConsent(version);
  }
}

export default function BusinessConsentGate({ source, children }: { source: ConsentSource; children: ReactNode }) {
  const { i18n } = useTranslation();
  const [phase, setPhase] = useState<Phase>("checking");
  const [failed, setFailed] = useState(false);
  const value = useMemo(() => ({ accepted: phase === "app", reopen: () => setPhase("screen") }), [phase]);

  useEffect(() => {
    let live = true;
    consentCopyVersion()
      .then((version) => source.consent(version))
      .then((found) => {
        if (live) setPhase(found.accepted_at ? "app" : "screen");
      })
      .catch(() => {
        if (live) setPhase("screen");
      });
    return () => {
      live = false;
    };
  }, [source]);

  const accept = () => {
    setPhase("saving");
    setFailed(false);
    const language = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language);
    consentCopyVersion()
      .then((version) => acceptWhereWorking(source, language, version))
      .then((saved) => {
        if (!saved.accepted_at) throw new Error("business_consent_not_saved");
        setPhase("app");
      })
      .catch(() => {
        setFailed(true);
        setPhase("screen");
      });
  };

  return (
    <BusinessConsentContext.Provider value={value}>
      {phase === "checking" || phase === "saving" ? <BusinessConsentLoading /> : null}
      {phase === "screen" ? <BusinessConsentScreen failed={failed} onContinue={accept} /> : null}
      {phase === "app" ? children : null}
    </BusinessConsentContext.Provider>
  );
}
