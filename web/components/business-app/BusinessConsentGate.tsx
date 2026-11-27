"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { getChosenGrant, grantNotLive, setChosenGrant } from "@/lib/business-grant";
import type { BusinessConsent } from "@/lib/business-api";
import { consentCopyVersion } from "@/lib/business-privacy-notice";
import { classifyFailure, referenceCode } from "@/lib/failure-screen";
import { normalizeEnabledLanguage, type ArgusLanguage } from "@/lib/language-features";
import type { BusinessDataSource } from "./business-data";
import { BusinessConsentContext } from "./business-consent-context";
import { BusinessConsentLoading, BusinessConsentScreen, type ConsentSave } from "./BusinessConsentScreen";

type Phase = { kind: "checking" } | { kind: "screen"; save: ConsentSave } | { kind: "app" };

type ConsentSource = Pick<BusinessDataSource, "consent" | "acceptConsent" | "ensureSpace">;

const spaceMissing = (error: unknown) => (error as { code?: unknown } | null)?.code === "business_space_missing";

/**
 * Saved where the server finds the person working: the chosen client's
 * Business, else their own, else the one that invited them. Only when the
 * server finds none of these does the person's own Business start, so an
 * invitee gets no Business of their own. A grant that died since it was
 * chosen is dropped first.
 */
async function acceptWhereWorking(source: ConsentSource, language: ArgusLanguage, version: string): Promise<BusinessConsent> {
  try {
    return await source.acceptConsent(version);
  } catch (error) {
    if (grantNotLive(error) && getChosenGrant()) {
      setChosenGrant(null);
      return acceptWhereWorking(source, language, version);
    }
    if (!spaceMissing(error)) throw error;
    await source.ensureSpace(language);
    return source.acceptConsent(version);
  }
}

/** Offline is the docked banner's to say, so the screen only goes back to idle. */
function failedSave(error: unknown): ConsentSave {
  if (classifyFailure(error, { online: navigator.onLine }) === "offline") return { kind: "idle" };
  return { kind: "failed", reference: referenceCode(error) };
}

export default function BusinessConsentGate({ source, children }: { source: ConsentSource; children: ReactNode }) {
  const { i18n } = useTranslation();
  const [phase, setPhase] = useState<Phase>({ kind: "checking" });
  const accepted = phase.kind === "app";
  const value = useMemo(() => ({ accepted, reopen: () => setPhase({ kind: "screen", save: { kind: "idle" } }) }), [accepted]);

  useEffect(() => {
    let live = true;
    source.consent(consentCopyVersion())
      .then((found) => {
        if (live) setPhase(found.accepted_at ? { kind: "app" } : { kind: "screen", save: { kind: "idle" } });
      })
      .catch(() => {
        if (live) setPhase({ kind: "screen", save: { kind: "idle" } });
      });
    return () => {
      live = false;
    };
  }, [source]);

  const accept = () => {
    if (phase.kind === "screen" && phase.save.kind === "saving") return;
    setPhase({ kind: "screen", save: { kind: "saving" } });
    const language = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language);
    acceptWhereWorking(source, language, consentCopyVersion())
      .then((saved) => {
        if (!saved.accepted_at) throw new Error("business_consent_not_saved");
        setPhase({ kind: "app" });
      })
      .catch((error: unknown) => setPhase({ kind: "screen", save: failedSave(error) }));
  };

  return (
    <BusinessConsentContext.Provider value={value}>
      {phase.kind === "checking" ? <BusinessConsentLoading /> : null}
      {phase.kind === "screen" ? <BusinessConsentScreen save={phase.save} onContinue={accept} /> : null}
      {phase.kind === "app" ? children : null}
    </BusinessConsentContext.Provider>
  );
}
