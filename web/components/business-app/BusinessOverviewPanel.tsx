"use client";

import WorkspaceSetupPreview from "@/app/design-workspace/WorkspaceSetupPreview";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { inboxCount, problemCount, readingCount } from "./inbox-count";
import { useBusiness } from "./BusinessWorkspace";
import BusinessAddMenu from "./BusinessAddMenu";
import BusinessMonthClosePanel, { useMonthCloseSource } from "./BusinessMonthClosePanel";
import HomeGreeting from "./foundation/HomeGreeting";
import { useHomeClock } from "./foundation/home-greeting";

export default function BusinessOverviewPanel() {
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, bridge, reload } = useBusiness();
  const porRevisar = inboxCount(records);
  const reading = readingCount(records) ?? 0;
  const problem = problemCount(records) ?? 0;
  const clock = useHomeClock(isBelowTablet);
  const monthClose = useMonthCloseSource();

  return (
    <section aria-labelledby="business-overview-title">
      {isBelowTablet ? <div data-testid="inicio-actions" className="mb-5 empty:hidden" style={{ paddingTop: 32 }}><BusinessAddMenu placement="page" /></div> : null}
      {process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? <WorkspaceSetupPreview /> : null}
      <BusinessMonthClosePanel
        monthClose={monthClose}
        headingAction={isBelowTablet ? undefined : <BusinessAddMenu placement="header" />}
        header={(switcher) => (
          <>
            <div data-testid="inicio-greeting-row" className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
              {isBelowTablet ? <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
                <HomeGreeting period={clock?.period ?? null} name={bridge?.greetingName} />
              </h2> : null}
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
    </section>
  );
}
