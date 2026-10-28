"use client";

import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { formatBusinessName } from "./business-format";
import { inboxCount, problemCount, readingCount } from "./inbox-count";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import BusinessMonthClosePanel, { useMonthCloseSource } from "./BusinessMonthClosePanel";
import HomeGreeting from "./foundation/HomeGreeting";
import { HomeHeading } from "./foundation/HomeHeading";
import { INICIO_REDESIGN_PREVIEW } from "./inicio/preview";
import { useHomeClock } from "./foundation/home-greeting";
import { PageDescription, usePageIntro } from "./foundation/PageHeading";
import { HomeCustomize, HomeSetupLead, HomeWork, useHomeOrder, type HomeSectionKey } from "./inicio/HomeOverviewDraft";

export default function BusinessOverviewPanel() {
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, bridge, reload, chosen, userId } = useBusiness();
  const { t } = useTranslation();
  const porRevisar = inboxCount(records);
  const reading = readingCount(records) ?? 0;
  const problem = problemCount(records) ?? 0;
  const clock = useHomeClock(isBelowTablet);
  const monthClose = useMonthCloseSource();
  const intro = usePageIntro("overview");
  // Design-lane draft of the new overview, local preview only; the month-close block stays below it, unchanged, for comparison.
  const overviewDraft = INICIO_REDESIGN_PREVIEW;
  const homeOrder = useHomeOrder(userId, chosen?.space_id);

  // The draft Home: bounded and centred, the greeting fixed first, then the person's own order of its three layers.
  const draftHome = (parts: { month: React.ReactNode; money: React.ReactNode }) => {
    const sections: Record<HomeSectionKey, React.ReactNode> = {
      work: <HomeWork />,
      ...parts,
    };
    return (
    <div data-testid="home-overview-draft" className="w-full space-y-6 pb-6">
      {/* From tablet up the greeting lives in the bar, on this container's edges; a phone shows it here. */}
      {isBelowTablet ? <HomeHeading name={bridge?.greetingName} business={formatBusinessName(chosen?.name, t("business.overview.title", "My business"))} /> : null}
      <HomeSetupLead />
      {homeOrder.order.map((key) => <div key={key} data-home-section={key}>{sections[key]}</div>)}
      <div className="flex border-t border-[color:var(--surface-divider)] pt-4"><HomeCustomize order={homeOrder.order} onChange={homeOrder.save} isDefault={homeOrder.isDefault} /></div>
    </div>
    );
  };

  const monthCloseBlock = (
    <BusinessMonthClosePanel
        monthClose={monthClose}
        // One Agregar per screen: with the overview draft it lives in the top bar; a phone keeps its page button.
        headingAction={isBelowTablet || overviewDraft ? undefined : <BusinessAddMenu placement="header" />}
        layout={overviewDraft ? "finance" : "inicio"}
        // Home lays out its three layers in the person's order; the panel hands over its month and money parts.
        arrange={overviewDraft ? ({ month, money }) => draftHome({ month, money }) : undefined}
        header={(switcher) => (
          <>
            <div data-testid="inicio-greeting-row" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              {isBelowTablet && !overviewDraft ? <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
                <HomeGreeting period={clock?.period ?? null} name={bridge?.greetingName} />
              </h2> : null}
              {/* The sentence stays with the greeting as one heading group; the month moves below it. From the tablet up the top bar carries it. */}
              {isBelowTablet && intro && !overviewDraft ? <div className="-mt-1 basis-full"><PageDescription text={intro.description} icon={intro.icon} /></div> : null}
              {switcher}
            </div>
          </>
        )}
        review={records.error ? (records.refused ? { state: "refused" } : { state: "failed", retry: reload }) : porRevisar === null ? { state: records.inbox === null ? "loading" : "unknown" } : {
          count: porRevisar,
          detail: null,
          reading,
          attention: problem,
          open: () => openPanel({ kind: "inbox" }),
        }}
      />
  );

  return (
    <section aria-labelledby="business-overview-title">
      {isBelowTablet ? <div data-testid="inicio-actions" className="mb-5 empty:hidden" style={{ paddingTop: 32 }}><BusinessAddMenu placement="page" /></div> : null}
      {monthCloseBlock}
    </section>
  );
}
