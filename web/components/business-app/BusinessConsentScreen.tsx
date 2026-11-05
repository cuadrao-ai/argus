"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { CuadraoLockup } from "@/components/CuadraoLockup";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { BANNER_HEIGHT_PX, ConnectionBanner, useOnline } from "@/components/ui/ConnectionBanner";
import { cuadraoLegalLinks } from "@/lib/cuadrao-legal-links";
import FullscreenLoading from "@/components/FullscreenLoading";
import { primaryButtonClass, quietButtonClass } from "./business-ui";

/** Where the one save stands. A failed save keeps the box ticked and offers one honest retry. */
export type ConsentSave = { kind: "idle" } | { kind: "saving" } | { kind: "failed"; reference: string };

export function BusinessConsentScreen({ save, onContinue }: { save: ConsentSave; onContinue: () => void }) {
  const { t } = useTranslation();
  const online = useOnline();
  const privacyUrl = cuadraoLegalLinks().privacy;
  const checkboxId = useId();
  const errorId = useId();
  const headingRef = useRef<HTMLHeadingElement>(null);
  const [optedIn, setOptedIn] = useState(false);
  const saving = save.kind === "saving";

  useEffect(() => {
    headingRef.current?.focus();
  }, []);

  return (
    <main
      data-testid="business-consent-screen"
      style={{ paddingTop: online ? undefined : BANNER_HEIGHT_PX }}
      className="relative min-h-[100dvh] w-full bg-[#F7F5EE] dark:bg-background"
    >
      {online ? null : <ConnectionBanner />}
      <div className="mx-auto flex w-full max-w-xl flex-col px-4 pb-12 pt-10 tablet:px-6 tablet:pt-20">
        <CuadraoLockup width={112} />
        <h1 ref={headingRef} tabIndex={-1} className="mt-10 font-display text-[28px] font-medium tracking-tight text-black outline-none dark:text-white">
          {t("business.consent.title")}
        </h1>
        <p className="mt-2 text-[14px] text-[#56635e] dark:text-white/65">{t("business.consent.one_time")}</p>
        <p className="mt-4 text-[16px] leading-relaxed text-black dark:text-white">{t("business.consent.body")}</p>
        <label htmlFor={checkboxId} className="mt-8 flex min-h-11 cursor-pointer items-start gap-3 text-[16px] leading-relaxed text-black dark:text-white">
          <input
            id={checkboxId}
            type="checkbox"
            className="mt-1 h-5 w-5 shrink-0 accent-[var(--cuadrao-green)]"
            checked={optedIn}
            disabled={saving}
            onChange={(event) => setOptedIn(event.target.checked)}
          />
          <span>{t("business.consent.opt_in")}</span>
        </label>
        {save.kind === "failed" ? (
          <div
            id={errorId}
            role="alert"
            data-testid="business-consent-error"
            className="mt-4 rounded-item border border-[#9e2f39]/30 bg-[#f6dfe0]/50 px-3.5 py-3 text-[14px] text-[#9e2f39] dark:border-[#ec9aa0]/30 dark:bg-[#ec9aa0]/10 dark:text-[#ec9aa0]"
          >
            <p>{t("business.consent.save_failed")}</p>
            <p className="mt-1"><ReferenceCode reference={save.reference} /></p>
            <button type="button" data-testid="business-consent-retry" className={`${quietButtonClass} -ml-1 mt-1`} disabled={!optedIn} onClick={onContinue}>
              {t("common.retry")}
            </button>
          </div>
        ) : null}
        <div className="mt-8 flex flex-col items-start gap-4">
          <button
            type="button"
            data-testid="business-consent-continue"
            className={`${primaryButtonClass} w-full aria-busy:cursor-progress tablet:w-auto`}
            disabled={!optedIn}
            aria-busy={saving || undefined}
            aria-describedby={save.kind === "failed" ? errorId : undefined}
            onClick={() => {
              if (!saving) onContinue();
            }}
          >
            {saving ? <Loader2 data-testid="business-consent-saving" className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {t("business.consent.continue")}
          </button>
          <a
            href={privacyUrl}
            target="_blank"
            rel="noreferrer"
            data-testid="business-consent-privacy"
            className={quietButtonClass}
          >
            {t("business.consent.privacy_link")}
          </a>
        </div>
      </div>
    </main>
  );
}

export function BusinessConsentLoading() {
  return <FullscreenLoading />;
}
