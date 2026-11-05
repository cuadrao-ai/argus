"use client";

import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { Briefcase, type Icon } from "@phosphor-icons/react";
import { SCREEN_ICON, type NavGlyph } from "../nav-glyphs";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";

/** The top-level screens that carry a one-sentence intro under their title. Inicio's greeting stands alone; nested sections and dialogs never have one. */
export type PageIntroScreen = Exclude<NavGlyph["name"], "overview"> | "business";

// Negocio is not in the rail; it carries the business mark's meaning, a briefcase.
const ICON: Record<PageIntroScreen, Icon> = { inbox: SCREEN_ICON.inbox, transactions: SCREEN_ICON.transactions, invoicing: SCREEN_ICON.invoicing, activity: SCREEN_ICON.activity, business: Briefcase };

const INTRO: Record<PageIntroScreen, { title: string; description: string }> = {
  inbox: { title: "business.inbox.title", description: "business.page_intro.inbox" },
  transactions: { title: "business.transactions.title", description: "business.page_intro.transactions" },
  invoicing: { title: "business.invoicing_preview.title", description: "business.page_intro.invoicing" },
  activity: { title: "business.nav.activity", description: "business.page_intro.activity" },
  business: { title: "business.settings.title", description: "business.page_intro.business" },
};

export function usePageIntro(screen: string | null | undefined) {
  const { t } = useTranslation();
  const intro = screen && screen in INTRO ? INTRO[screen as PageIntroScreen] : null;
  if (!intro) return null;
  // The sentence carries the same icon the rail uses for the screen.
  const Icon = ICON[screen as PageIntroScreen];
  return { title: t(intro.title), description: t(intro.description), icon: <Icon size="1em" /> };
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
 * the title and its sentence (BusinessHeader), so this renders nothing there.
 */
export function PageHeading({ screen }: { screen: PageIntroScreen }) {
  const intro = usePageIntro(screen);
  const { isBelowTablet: phone } = useResponsiveLayout();
  if (!phone || !intro) return null;
  return (
    <div data-testid="business-page-heading" className="mb-[34px]">
      <h2 className="mb-2 font-display text-[26px] font-medium leading-tight tracking-tight text-black dark:text-white">{intro.title}</h2>
      <PageDescription text={intro.description} icon={intro.icon} />
    </div>
  );
}
