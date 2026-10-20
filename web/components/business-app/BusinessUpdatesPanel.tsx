"use client";

import { useEffect, useState, type MouseEvent } from "react";
import { useTranslation } from "react-i18next";
import type { BusinessUpdate, ReceiptStatus } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { EmptyState } from "./foundation/EmptyState";
import { formatRelativeTime } from "./business-format";
import { lockedCardClass, StatusPill, useAttentionLabel } from "./business-ui";
import { Settle } from "./business-skeletons";

const KIND_STATUS: Record<BusinessUpdate["kind"], ReceiptStatus> = {
  receipt_ready: "review_ready",
  receipt_needs_attention: "needs_attention",
  expense_confirmed: "confirmed",
};

function opensInPlace(event: MouseEvent) {
  return event.button === 0 && !event.metaKey && !event.ctrlKey && !event.shiftKey && !event.altKey;
}

/**
 * Updates are read from the receipts' and expenses' own states. There is no
 * separate notification store, so there is no unread count to fall out of step.
 */
export default function BusinessUpdatesPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const attentionLabel = useAttentionLabel();
  const { source, revision, openPanel, actions, chosen, spaces } = useBusiness();
  const add = chosen?.role === "owner" ? actions.create.find((action) => action.id === "upload_receipt") : undefined;
  const [items, setItems] = useState<BusinessUpdate[] | null>(null);
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    source
      .updates()
      .then((next) => {
        if (cancelled) return;
        setItems(next);
        setFailed(false);
      })
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [attempt, revision, source]);

  const sentence = (update: BusinessUpdate) =>
    update.kind === "receipt_needs_attention"
      ? attentionLabel(update.attention)
      : update.kind === "receipt_ready"
        ? t("business.updates.ready_line", "Ready to review")
        : t("business.updates.confirmed_line", "Saved as an expense");

  const row = (update: BusinessUpdate) => {
    const line = sentence(update);
    const content = (
      <>
        <span className="row-span-2 flex items-start tablet:row-span-1">
          <StatusPill status={KIND_STATUS[update.kind]} />
        </span>
        <span className="min-w-0 break-words text-[15px] font-medium leading-[22px] text-[#172b26] dark:text-white">
          {update.label ?? t("business.receipt.untitled", "Receipt")}
        </span>
        {line ? (
          <span className="col-start-2 min-w-0 break-words text-[13px] leading-[18px] text-[#56635e] desktop:truncate dark:text-white/60">{line}</span>
        ) : null}
        <time
          dateTime={update.occurred_at}
          className="col-start-2 row-start-3 whitespace-nowrap text-[13px] leading-[18px] text-[#56635e] tablet:col-start-3 tablet:row-start-1 tablet:text-right dark:text-white/60"
        >
          {formatRelativeTime(update.occurred_at, locale)}
        </time>
      </>
    );
    const rowClass = "col-span-full grid min-h-16 grid-cols-subgrid content-start gap-y-1 rounded-[12px] px-3 py-3";
    const receiptId = update.receipt_id;
    return (
      <li key={update.id} data-testid="business-update-row" className="col-span-full grid grid-cols-subgrid">
        {receiptId ? (
          <a
            href={`?receipt=${encodeURIComponent(receiptId)}`}
            onClick={(event) => {
              if (!opensInPlace(event)) return;
              event.preventDefault();
              openPanel({ kind: "receipt", receiptId });
            }}
            className={rowClass}
          >
            {content}
          </a>
        ) : (
          <div className={rowClass}>{content}</div>
        )}
      </li>
    );
  };

  return (
    <section>
      <div className="mb-6 min-w-0">
        <h1 className="font-display text-[28px] font-medium leading-[34px] text-[#172b26] dark:text-white">
          {t("business.updates.title", "Updates")}
        </h1>
        <p className="mt-1 text-[13px] leading-[18px] text-[#56635e] dark:text-white/60">
          {t("business.updates.subtitle", "Processing results and anything that needs you.")}
        </p>
      </div>
      {failed ? (
        <EmptyState kind="error" testId="business-updates-error" title={t("business.empty.updates_error", "We couldn't load updates")} body={t("business.empty.error_body", "Your data is still saved. Check your connection and try again.")} action={{ label: t("common.retry", "Retry"), run: () => { setFailed(false); setAttempt((value) => value + 1); } }} />
      ) : null}
      {/* Hold until the Business is known, so an empty feed shows its action from the first frame. */}
      <Settle pending={(items === null || spaces === null) && !failed} layout="updates">
        {items === null || spaces === null ? null : items.length === 0 ? (
          <div data-testid="business-updates-empty" className={`${lockedCardClass} px-6`}>
            <EmptyState kind="first_run" mark="bell" compact title={t("business.empty.updates_title", "See what happened to your receipts")} body={t("business.empty.updates_body", "When Cuadrao reads, saves or needs something from a receipt, it shows up here.")} action={add ? { label: add.label, run: add.run } : undefined} />
          </div>
        ) : (
          <ul
            data-testid="business-updates-list"
            className={`${lockedCardClass} grid grid-cols-[auto_minmax(0,1fr)] gap-x-3 divide-y divide-[#DCE0DA] p-2 tablet:grid-cols-[auto_minmax(0,1fr)_auto] dark:divide-white/[0.06]`}
          >
            {items.map(row)}
          </ul>
        )}
      </Settle>
    </section>
  );
}
