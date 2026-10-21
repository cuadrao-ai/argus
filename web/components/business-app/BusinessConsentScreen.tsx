"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "@/components/CuadraoLockup";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { normalizeEnabledLanguage } from "@/lib/language-features";
import { noticeParagraphs, privacyNoticePublished, type PrivacyNoticeLocale } from "@/lib/business-privacy-notice";
import { BusinessSkeleton } from "./business-skeletons";
import { primaryButtonClass, quietButtonClass } from "./business-ui";

export function BusinessConsentScreen({
  failed,
  onContinue,
}: {
  failed: boolean;
  onContinue: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language) as PrivacyNoticeLocale;
  const published = privacyNoticePublished(locale);
  const checkboxId = useId();
  const errorId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const privacyRef = useRef<HTMLButtonElement>(null);
  const [optedIn, setOptedIn] = useState(false);
  const [noticeOpen, setNoticeOpen] = useState(false);

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <main data-testid="business-consent-screen" className="min-h-[100dvh] w-full bg-[#F7F5EE] dark:bg-background">
      <div className="mx-auto flex w-full max-w-xl flex-col px-4 pb-12 pt-10 tablet:px-6 tablet:pt-20">
        <CuadraoLockup width={112} />
        <h1 ref={headingRef} tabIndex={-1} className="mt-10 font-display text-[28px] font-medium tracking-tight text-black outline-none dark:text-white">
          {t("business.consent.title")}
        </h1>
        <p className="mt-4 text-[16px] leading-relaxed text-black dark:text-white">{t("business.consent.body")}</p>
        <label htmlFor={checkboxId} className="mt-8 flex min-h-11 cursor-pointer items-start gap-3 text-[16px] leading-relaxed text-black dark:text-white">
          <input
            id={checkboxId}
            type="checkbox"
            className="mt-1 h-5 w-5 shrink-0 accent-[var(--cuadrao-green)]"
            checked={optedIn}
            onChange={(event) => setOptedIn(event.target.checked)}
          />
          <span>{t("business.consent.opt_in")}</span>
        </label>
        {failed ? (
          <p id={errorId} role="alert" className="mt-3 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">
            {t("settings.data.personalization.errors.edit")}
          </p>
        ) : null}
        <div className="mt-8 flex flex-col items-start gap-4">
          <button
            type="button"
            data-testid="business-consent-continue"
            className={`${primaryButtonClass} w-full tablet:w-auto`}
            disabled={!optedIn}
            aria-describedby={failed ? errorId : undefined}
            onClick={onContinue}
          >
            {t("business.consent.continue")}
          </button>
          {published ? (
            <button
              ref={privacyRef}
              type="button"
              data-testid="business-consent-privacy"
              className={quietButtonClass}
              onClick={() => setNoticeOpen(true)}
            >
              {t("business.consent.privacy_link")}
            </button>
          ) : null}
        </div>
      </div>
      {noticeOpen ? (
        <AdaptivePanel
          title={t("business.privacy_notice.title")}
          closeLabel={t("business.privacy_notice.close")}
          onClose={() => setNoticeOpen(false)}
          returnFocusRef={privacyRef}
          width="lg"
        >
          <div className="space-y-4 px-4 pb-6 text-[16px] leading-relaxed text-black dark:text-white" data-testid="business-privacy-notice">
            {noticeParagraphs(locale).map((paragraph) => (
              <p key={paragraph}>{paragraph}</p>
            ))}
          </div>
        </AdaptivePanel>
      ) : null}
    </main>
  );
}

/** Inicio's layout while the gate checks or saves, so /biz never paints blank. */
export function BusinessConsentLoading() {
  return (
    <main data-testid="business-consent-loading" className="mx-auto w-full max-w-3xl px-4 pb-12 pt-10 tablet:px-6 tablet:pt-20">
      <BusinessSkeleton layout="overview" />
    </main>
  );
}
