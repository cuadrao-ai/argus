"use client";

import { CuadraoLockup } from "@/components/CuadraoLockup";
import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";

type LegalPageKind = "terms" | "privacy";

type AlphaLegalPageProps = {
  kind: LegalPageKind;
  supportEmail: string;
};

// A "list" section renders an intro, labelled entries, then a closing note.
// Storage disclosure is only readable when each category is named separately.
type LegalSection = {
  key: string;
  variant?: "list";
};

const LEGAL_SECTIONS: Record<LegalPageKind, LegalSection[]> = {
  terms: [
    { key: "no_investment_advice" },
    { key: "no_brokerage" },
    { key: "historical_simulations" },
    { key: "early_access_changes" },
    { key: "eligibility" },
    { key: "acceptable_use" },
    { key: "third_party_services" },
    { key: "account_support" },
  ],
  privacy: [
    { key: "data_collect" },
    { key: "data_use" },
    { key: "ai_market_data" },
    { key: "infrastructure" },
    { key: "cookies", variant: "list" },
    { key: "access_retention" },
    { key: "your_controls" },
    { key: "sale_personal_info" },
  ],
};

// Every browser-state writer gets its own entry. Both the frontend and the
// backend set cookies, so this list is not derivable from web/ alone.
const LIST_SECTION_ITEMS: Record<string, readonly string[]> = {
  cookies: ["sign_in", "guest_handoff", "security", "preferences"],
};

const BODY_CLASS = "text-[15px] leading-7 text-black/65 dark:text-white/65";

export default function AlphaLegalPage({
  kind,
  supportEmail,
}: AlphaLegalPageProps) {
  const { t } = useTranslation();
  const alternateHref = kind === "terms" ? "/privacy" : "/terms";
  const alternateLabel = t(
    kind === "terms" ? "legal.privacy.title" : "legal.terms.title",
  );
  const backLabel = t("legal.back_to_argus");

  return (
    <main className="min-h-[100dvh] bg-white text-[#191c1f] dark:bg-[#191c1f] dark:text-white">
      <div className="mx-auto flex w-full max-w-3xl flex-col px-6 py-8 md:px-8 md:py-12">
        <header className="flex items-center justify-between gap-4 border-b border-black/10 pb-5 dark:border-white/10">
          <Link
            href="/"
            aria-label={backLabel}
            title={backLabel}
            className="group inline-flex items-center gap-2 text-black dark:text-white"
          >
            <ArrowLeft
              aria-hidden="true"
              className="h-4 w-4 text-black/40 transition-all group-hover:-translate-x-0.5 group-hover:text-black dark:text-white/40 dark:group-hover:text-white"
            />
            <CuadraoLockup width={96} />
          </Link>
          <Link
            href={alternateHref}
            className="rounded-full border border-black/10 px-4 py-2 text-[13px] font-medium text-black/70 transition-colors hover:border-black/25 hover:text-black dark:border-white/15 dark:text-white/70 dark:hover:border-white/30 dark:hover:text-white"
          >
            {alternateLabel}
          </Link>
        </header>

        <section className="pt-14 md:pt-20">
          <p className="mb-4 text-[12px] font-medium tracking-[0] text-black/45 dark:text-white/45">
            {t("legal.eyebrow")}
          </p>
          <h1 className="font-display max-w-[720px] text-[42px] font-medium leading-[1.05] tracking-[0] text-black dark:text-white md:text-[56px]">
            {t(`legal.${kind}.title`)}
          </h1>
          <p className="mt-4 text-[14px] font-medium text-black/45 dark:text-white/45">
            {t("legal.effective_date")}
          </p>
          <p className="mt-8 max-w-[680px] text-[17px] leading-8 text-black/65 dark:text-white/65">
            {t(`legal.${kind}.intro`)}
          </p>
        </section>

        <div className="mt-12 space-y-10 border-t border-black/10 pt-10 dark:border-white/10">
          {LEGAL_SECTIONS[kind].map((section) => (
            <section key={section.key}>
              <h2 className="font-display text-[24px] font-medium tracking-[0]">
                {t(`legal.${kind}.sections.${section.key}.title`)}
              </h2>
              {section.variant === "list" ? (
                <LegalSectionList t={t} kind={kind} sectionKey={section.key} />
              ) : (
                <p className={`mt-3 ${BODY_CLASS}`}>
                  {renderLegalBody(t, kind, section.key, supportEmail)}
                </p>
              )}
            </section>
          ))}
        </div>

        <footer className="mt-14 flex flex-col gap-3 border-t border-black/10 pt-6 text-[13px] text-black/45 dark:border-white/10 dark:text-white/45 sm:flex-row sm:items-center sm:justify-between">
          <span>{t("legal.footer_label")}</span>
          <Link
            href="/"
            className="font-medium text-black/70 transition-colors hover:text-black dark:text-white/70 dark:hover:text-white"
          >
            {backLabel}
          </Link>
        </footer>
      </div>
    </main>
  );
}

function LegalSectionList({
  t,
  kind,
  sectionKey,
}: {
  t: TFunction;
  kind: LegalPageKind;
  sectionKey: string;
}) {
  const key = `legal.${kind}.sections.${sectionKey}`;
  const items = LIST_SECTION_ITEMS[sectionKey] ?? [];

  return (
    <>
      <p className={`mt-3 ${BODY_CLASS}`}>{t(`${key}.body`)}</p>
      <dl className="mt-5 space-y-4 border-l border-black/10 pl-5 dark:border-white/10">
        {items.map((item) => (
          <div key={item}>
            <dt className="text-[15px] font-medium text-black dark:text-white">
              {t(`${key}.items.${item}.label`)}
            </dt>
            <dd className={`mt-1 ${BODY_CLASS}`}>
              {t(`${key}.items.${item}.body`)}
            </dd>
          </div>
        ))}
      </dl>
      <p className={`mt-5 ${BODY_CLASS}`}>{t(`${key}.body_after`)}</p>
    </>
  );
}

function renderLegalBody(
  t: TFunction,
  kind: LegalPageKind,
  sectionKey: string,
  supportEmail: string,
) {
  const key = `legal.${kind}.sections.${sectionKey}`;
  const supportEmailLink = (
    <a
      className="font-medium text-black underline decoration-black/25 underline-offset-4 transition-colors hover:decoration-black dark:text-white dark:decoration-white/30 dark:hover:decoration-white"
      href={`mailto:${supportEmail}`}
    >
      {supportEmail}
    </a>
  );

  if (
    (kind === "terms" && sectionKey === "account_support") ||
    (kind === "privacy" && sectionKey === "your_controls")
  ) {
    return (
      <>
        {t(`${key}.body_before_email`)} {supportEmailLink}
        {t(`${key}.body_after_email`)}
      </>
    );
  }

  return t(`${key}.body`);
}
