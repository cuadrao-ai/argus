"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import {
  BUSINESS_PRIVACY_NOTICE_VERSION,
  canSubmitAcceptance,
  noticePlainText,
  sha256Hex,
  type PrivacyNoticeLocale,
} from "@/lib/business-privacy-notice";
import type { BusinessPrivacyNoticeClient } from "@/lib/business-privacy-notice-client";
import { cardClass, primaryButtonClass, secondaryButtonClass } from "./business-ui";

function paragraphsOf(value: unknown): string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string" && item.length > 0) ? value : [];
}

function ConsentFrame({
  title,
  children,
  testId,
}: {
  title: string;
  children: ReactNode;
  testId: string;
}) {
  const headingRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    headingRef.current?.focus();
  }, [title]);
  return (
    <main className="mx-auto flex min-h-[100dvh] w-full max-w-xl flex-col justify-center px-4 py-8" data-testid={testId}>
      <div className={cardClass}>
        <h1 ref={headingRef} tabIndex={-1} className="font-display text-[28px] font-medium tracking-tight text-black outline-none dark:text-white">
          {title}
        </h1>
        {children}
      </div>
    </main>
  );
}

export function BusinessConsentScreen({
  userId,
  client,
  onAccepted,
  onDecline,
}: {
  userId: string;
  client: BusinessPrivacyNoticeClient;
  onAccepted: () => void;
  onDecline: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language) as PrivacyNoticeLocale;
  const paragraphs = paragraphsOf(t("business.privacy_notice.paragraphs", { returnObjects: true }));
  const title = t("business.consent.title");
  const ready = title.length > 0 && paragraphs.length > 0;
  const checkboxId = useId();
  const errorId = useId();
  const privacyRef = useRef<HTMLButtonElement>(null);
  const [optedIn, setOptedIn] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);
  const [saving, setSaving] = useState(false);
  const [failed, setFailed] = useState(false);

  const accept = async () => {
    if (!canSubmitAcceptance(optedIn, saving) || !ready) return;
    setSaving(true);
    setFailed(false);
    try {
      await client.accept({
        userId,
        noticeVersion: BUSINESS_PRIVACY_NOTICE_VERSION,
        locale,
        textSha256: await sha256Hex(noticePlainText(paragraphs)),
      });
      onAccepted();
    } catch {
      setFailed(true);
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <ConsentFrame title={title} testId="business-consent-screen">
        <p className="mt-3 text-[16px] leading-relaxed text-black dark:text-white">
          {t("business.consent.intro")}
        </p>
        <p className="mt-3 text-[14px] text-black/80 dark:text-white/80">
          {t("business.consent.version_label", { version: BUSINESS_PRIVACY_NOTICE_VERSION })}
        </p>
        <button
          ref={privacyRef}
          type="button"
          className="mt-4 inline-flex min-h-11 items-center text-[16px] font-medium text-black underline underline-offset-4 dark:text-white"
          onClick={() => setNoticeOpen(true)}
        >
          {t("business.consent.privacy_link")}
        </button>
        <div className="mt-6">
          <label htmlFor={checkboxId} className="flex min-h-11 cursor-pointer items-start gap-3 text-[16px] leading-relaxed text-black dark:text-white">
            <input
              id={checkboxId}
              type="checkbox"
              className="mt-1 h-5 w-5 shrink-0 accent-black dark:accent-white"
              checked={optedIn}
              disabled={!ready || saving}
              onChange={(event) => setOptedIn(event.target.checked)}
            />
            <span>{t("business.consent.opt_in")}</span>
          </label>
        </div>
        {failed ? (
          <p id={errorId} role="alert" className="mt-3 text-[14px] text-[#a8434c] dark:text-[#ec9aa0]">
            {t("business.consent.save_error")}
          </p>
        ) : null}
        <div className="mt-6 flex flex-col gap-3">
          <button
            type="button"
            data-testid="business-consent-accept"
            className={primaryButtonClass}
            disabled={!canSubmitAcceptance(optedIn && ready, saving)}
            aria-describedby={failed ? errorId : undefined}
            onClick={() => void accept()}
          >
            {saving ? t("business.consent.saving") : t("business.consent.accept")}
          </button>
          <button
            type="button"
            data-testid="business-consent-decline"
            className={secondaryButtonClass}
            disabled={saving}
            onClick={onDecline}
          >
            {t("business.consent.decline")}
          </button>
        </div>
      </ConsentFrame>
      {noticeOpen ? (
        <AdaptivePanel
          title={t("business.privacy_notice.title")}
          closeLabel={t("business.privacy_notice.close")}
          onClose={() => setNoticeOpen(false)}
          returnFocusRef={privacyRef}
          width="lg"
        >
          <div className="space-y-4 px-4 pb-6 text-[16px] leading-relaxed text-black dark:text-white" data-testid="business-privacy-notice">
            {paragraphs.map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        </AdaptivePanel>
      ) : null}
    </>
  );
}

export function BusinessConsentDeclined({ onBack, onContinue }: { onBack: () => void; onContinue: () => void }) {
  const { t } = useTranslation();
  return (
    <ConsentFrame title={t("business.consent.decline_title")} testId="business-consent-declined">
      <p className="mt-3 text-[16px] leading-relaxed text-black dark:text-white">
        {t("business.consent.decline_body")}
      </p>
      <div className="mt-6 flex flex-col gap-3">
        <button type="button" className={primaryButtonClass} data-testid="business-consent-continue-without" onClick={onContinue}>
          {t("business.consent.continue_without")}
        </button>
        <button type="button" className={secondaryButtonClass} onClick={onBack}>
          {t("business.consent.back")}
        </button>
      </div>
    </ConsentFrame>
  );
}

export function BusinessConsentAccepted({ onContinue }: { onContinue: () => void }) {
  const { t } = useTranslation();
  return (
    <ConsentFrame title={t("business.consent.accepted_title")} testId="business-consent-accepted">
      <p className="mt-3 text-[16px] leading-relaxed text-black dark:text-white">
        {t("business.consent.accepted_body")}
      </p>
      <button type="button" className={`${primaryButtonClass} mt-6`} data-testid="business-consent-continue" onClick={onContinue}>
        {t("business.consent.continue")}
      </button>
    </ConsentFrame>
  );
}

export function BusinessConsentHeld({ onReview }: { onReview: () => void }) {
  const { t } = useTranslation();
  return (
    <div role="status" data-testid="business-consent-held" className="border-b border-black/10 bg-[#f6f4ef] px-4 py-3 text-black dark:border-white/10 dark:bg-[#1f2225] dark:text-white">
      <p className="text-[15px] leading-relaxed">{t("business.consent.held")}</p>
      <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={onReview}>
        {t("business.consent.review")}
      </button>
    </div>
  );
}
