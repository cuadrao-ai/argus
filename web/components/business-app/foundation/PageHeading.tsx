"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase } from "@phosphor-icons/react";
import type { NavGlyph } from "../nav-glyphs";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";

export type PageHeadingScreen = Exclude<NavGlyph["name"], "overview"> | "business";

const TITLE: Record<PageHeadingScreen, string> = {
  inbox: "business.inbox.title",
  transactions: "business.transactions.title",
  invoicing: "business.invoicing_preview.title",
  activity: "business.nav.activity",
  business: "business.settings.title",
};

export function usePageHeading(screen: string | null | undefined) {
  const { t } = useTranslation();
  const title = screen && screen in TITLE ? TITLE[screen as PageHeadingScreen] : null;
  if (!title) return null;
  return {
    title: t(title),
    description: screen === "business" ? t("business.page_intro.business") : null,
    icon: screen === "business" ? <Briefcase size="1em" /> : null,
  };
}

/** The sentence under a screen's title: body size, regular, secondary color; it wraps and never truncates. */
export function PageDescription({ text, icon }: { text: string; icon?: ReactNode }) {
  return (
    <p data-testid="business-page-description" className="flex max-w-[60ch] items-start gap-2 text-[16px] font-normal leading-6 text-[#56635e] dark:text-white/70">
      {/* The icon keeps 1em and sits on the first line's middle, whatever the wrap. */}
      {icon ? <span aria-hidden="true" className="flex h-6 shrink-0 items-center">{icon}</span> : null}
      <span>{text}</span>
    </p>
  );
}

/**
 * A phone's heading group at the top of a screen. From the tablet stop up the top bar holds
 * the title and optional settings intro (BusinessHeader), so this renders nothing there.
 */
export function PageHeading({ screen }: { screen: PageHeadingScreen }) {
  const heading = usePageHeading(screen);
  const { isBelowTablet: phone } = useResponsiveLayout();
  if (!phone || !heading) return null;
  return (
    <div data-testid="business-page-heading" className="mb-[34px]">
      <h2 className={`${heading.description ? "mb-2 " : ""}font-display text-[26px] font-medium leading-tight tracking-tight text-black dark:text-white`}>{heading.title}</h2>
      {heading.description ? <PageDescription text={heading.description} icon={heading.icon} /> : null}
    </div>
  );
}
