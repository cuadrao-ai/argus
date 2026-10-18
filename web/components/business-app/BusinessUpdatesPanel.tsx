"use client";

import { useEffect, useState } from "react";
import { AlertCircle, CheckCircle2, CircleDashed } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { BusinessUpdate } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatRelativeTime } from "./business-format";
import { cardClass, PanelHeading, useAttentionLabel } from "./business-ui";
import { Settle } from "./business-skeletons";

/**
 * Updates are read from the receipts' and expenses' own states. There is no
 * separate notification store, so there is no unread count to fall out of step.
 */
export default function BusinessUpdatesPanel() {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? "en";
  const attentionLabel = useAttentionLabel();
  const { source, revision, openPanel } = useBusiness();
  const [items, setItems] = useState<BusinessUpdate[] | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    source
      .updates()
      .then((next) => !cancelled && setItems(next))
      .catch(() => !cancelled && setFailed(true));
    return () => {
      cancelled = true;
    };
  }, [revision, source]);

  const describe = (update: BusinessUpdate) => {
    const name = update.label ?? t("business.receipt.untitled", "Receipt");
    if (update.kind === "receipt_ready") {
      return { Icon: CircleDashed, tone: "text-black/45 dark:text-white/45", text: t("business.updates.ready", "{{name}} is ready to review", { name }) };
    }
    if (update.kind === "receipt_needs_attention") {
      return { Icon: AlertCircle, tone: "text-[#d66d75]", text: `${t("business.updates.attention", "{{name}} needs attention", { name })}. ${attentionLabel(update.attention)}` };
    }
    return { Icon: CheckCircle2, tone: "text-black/45 dark:text-white/45", text: t("business.updates.confirmed", "{{name}} was saved as an expense", { name }) };
  };

  return (
    <section>
      <PanelHeading
        title={t("business.updates.title", "Updates")}
        subtitle={t("business.updates.subtitle", "Processing results and anything that needs you.")}
      />
      {failed ? (
        <p role="alert" className="text-[14px] text-black/70 dark:text-white/70">
          {t("business.updates.error", "We couldn't load updates. Try again.")}
        </p>
      ) : (
        <Settle pending={items === null} layout="updates">
          {items === null ? null : items.length === 0 ? (
        <div className={`${cardClass} text-center text-[14px] text-black/55 dark:text-white/55`}>
          {t("business.updates.empty", "Nothing new. Results from your receipts will appear here.")}
        </div>
      ) : (
        <ul className={`${cardClass} divide-y divide-black/[0.05] p-2 dark:divide-white/[0.05]`}>
          {items.map((update) => {
            const { Icon, tone, text } = describe(update);
            return (
              <li key={update.id}>
                <button
                  type="button"
                  disabled={!update.receipt_id}
                  onClick={() => update.receipt_id && openPanel({ kind: "receipt", receiptId: update.receipt_id })}
                  className="flex w-full items-start gap-3 rounded-[16px] px-3 py-3 text-left hover:bg-black/[0.03] focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/[0.04]"
                >
                  <Icon className={`mt-0.5 h-5 w-5 shrink-0 ${tone}`} />
                  <span className="min-w-0 flex-1 text-[14px] text-black/80 dark:text-white/80">{text}</span>
                  <span className="shrink-0 text-[12px] text-black/45 dark:text-white/45">
                    {formatRelativeTime(update.occurred_at, locale)}
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
          )}
        </Settle>
      )}
    </section>
  );
}
