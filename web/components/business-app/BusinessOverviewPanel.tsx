"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import StarterActions from "@/components/chat/StarterActions";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { businessReceivingAddress } from "@/lib/business-email";
import { countPorRevisar, countReviewBucket } from "@/lib/business-review-count";
import { useBusiness } from "./BusinessWorkspace";
import { formatBusinessName } from "./business-format";
import { cardClass, pillButtonClass, secondaryButtonClass } from "./business-ui";
import BusinessMonthClosePanel from "./BusinessMonthClosePanel";

function ForwardCard() {
  const { t } = useTranslation();
  const { source } = useBusiness();
  const [address, setAddress] = useState<string | null>(null);
  useEffect(() => {
    if (!source?.emailIntake) return undefined;
    let live = true;
    source.emailIntake().then((intake) => {
      if (live) setAddress(businessReceivingAddress(intake));
    }).catch(() => {
      if (live) setAddress(null);
    });
    return () => {
      live = false;
    };
  }, [source]);
  if (!address) return null;
  return (
    <section data-testid="inicio-forward" className={`${cardClass} mt-6`}>
      <h3 className="font-display text-[16px] font-medium text-black dark:text-white">{t("business.email.forward_to", "Forward receipts to this address:")}</h3>
      <p data-testid="inicio-forward-address" className="mt-2 break-all text-[14px] text-black/70 dark:text-white/70">{address}</p>
      <button
        type="button"
        data-testid="inicio-forward-copy"
        className={`${secondaryButtonClass} mt-3 min-w-11`}
        onClick={() => { void navigator.clipboard?.writeText(address); }}
      >
        {t("business.email.copy", "Copy address")}
      </button>
    </section>
  );
}

export default function BusinessOverviewPanel() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const { records, openPanel, actions, chosen } = useBusiness();
  const owner = chosen?.role !== "accountant";
  const upload = owner ? actions.create?.find((action) => action.id === "upload_receipt") ?? null : null;
  const items = records.inbox;
  const porRevisar = items ? countPorRevisar(items) : null;
  const reading = items ? countReviewBucket(items, "reading") : 0;
  const problem = items ? countReviewBucket(items, "unreadable") : 0;
  const primaryClass = `${pillButtonClass} min-w-11 bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]`;

  return (
    <section aria-labelledby="business-overview-title">
      <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
        <h2 id="business-overview-title" className="font-display text-[26px] font-medium tracking-tight text-black dark:text-white">
          {formatBusinessName(chosen?.name, t("business.overview.title", "My business"))}
        </h2>
        <div className="flex flex-wrap items-center justify-end gap-3">
          {upload ? (
            <button type="button" data-testid="business-primary-upload" data-primary="true" className={primaryClass} onClick={upload.run}>
              {upload.label}
            </button>
          ) : chosen?.role === "accountant" ? (
            <button type="button" data-testid="inicio-primary-review" data-primary="true" className={primaryClass} onClick={() => openPanel({ kind: "inbox" })}>
              {t("business.actions.review_receipts", "Review receipts")}
            </button>
          ) : null}
        </div>
      </div>

      <button
        type="button"
        data-testid="inicio-por-revisar"
        onClick={() => openPanel({ kind: "inbox" })}
        className={`${cardClass} mb-6 flex min-h-11 w-full flex-col items-start justify-center text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)]/40`}
      >
        <span className="font-display text-[20px] font-medium text-black dark:text-white">
          {porRevisar === null
            ? t("business.overview.open_inbox", "Open inbox")
            : porRevisar === 0
              ? t("business.overview.por_revisar_none", "Nothing to review")
              : <><span data-testid="inicio-por-revisar-count">{porRevisar}</span>{" "}{t("business.overview.por_revisar", "to review")}</>}
        </span>
        {reading > 0 || problem > 0 ? (
          <span data-testid="inicio-otras" className="mt-1 text-[14px] text-black/70 dark:text-white/75">
            {[
              reading > 0 ? t("business.overview.reading", { count: reading }) : null,
              problem > 0 ? t("business.overview.problem", { count: problem }) : null,
            ].filter(Boolean).join(" · ")}
          </span>
        ) : null}
      </button>

      <BusinessMonthClosePanel />

      {records.error ? (
        <div role="alert" className={`${cardClass} mt-6 text-[14px] text-black/70 dark:text-white/70`}>
          {t("business.overview.error", "We couldn't load your business records. Your saved receipts and expenses are safe. Try again.")}
        </div>
      ) : null}

      <ForwardCard />

      <div className="mt-8">
        <StarterActions
          onSelect={() => undefined}
          entries={actions.starterEntries.filter((entry) => entry.key !== "upload_receipt" && entry.key !== "review_inbox")}
          layout={isBelowTablet ? "scroll" : "wrap"}
        />
      </div>
    </section>
  );
}
