"use client";

import { useCallback, useEffect, useState, type RefObject } from "react";
import { Check, Copy, ExternalLink, Link2, Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import {
  copyReceiptLink,
  listEvidenceReceipts,
  receiptUrl,
  revokeEvidenceReceipt,
  type EvidenceReceipt,
} from "@/lib/evidence-receipts";
import { localeForLanguage, normalizeEnabledLanguage } from "@/lib/language-features";

type SharedReceiptsViewProps = {
  onClose: () => void;
  /** Present on a child panel; returns to Data Controls instead of dismissing. */
  onBack?: () => void;
  backLabel?: string;
  returnFocusRef?: RefObject<HTMLElement | null>;
};

/**
 * The receipt list, in Data Controls.
 *
 * This is the control that makes owner-revocable true in practice rather than
 * only in the API. The largest part of the ChatGPT exposure was that people could
 * not see what they had shared, so they were surprised by links they had
 * forgotten creating.
 */
export default function SharedReceiptsView({
  onClose,
  onBack,
  backLabel,
  returnFocusRef,
}: SharedReceiptsViewProps) {
  const { t, i18n } = useTranslation();
  const [receipts, setReceipts] = useState<EvidenceReceipt[]>([]);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isLoadingMore, setIsLoadingMore] = useState(false);
  const [loadFailed, setLoadFailed] = useState(false);
  const [confirmingId, setConfirmingId] = useState<string | null>(null);
  const [revokingId, setRevokingId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(() => {
    setIsLoading(true);
    setLoadFailed(false);
    listEvidenceReceipts()
      .then((page) => {
        setReceipts(page.items);
        setNextCursor(page.next_cursor);
      })
      .catch(() => setLoadFailed(true))
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(load, [load]);

  const loadMore = async () => {
    if (!nextCursor) return;
    setIsLoadingMore(true);
    setActionError(null);
    try {
      const page = await listEvidenceReceipts(nextCursor);
      setReceipts((previous) => [...previous, ...page.items]);
      setNextCursor(page.next_cursor);
    } catch {
      setActionError(
        t("receipt.list.load_error", "Your shared links did not load."),
      );
    } finally {
      setIsLoadingMore(false);
    }
  };

  const revoke = async (receipt: EvidenceReceipt) => {
    setRevokingId(receipt.id);
    setActionError(null);
    try {
      const updated = await revokeEvidenceReceipt(receipt.id);
      setReceipts((previous) =>
        previous.map((item) => (item.id === updated.id ? updated : item)),
      );
      setConfirmingId(null);
    } catch {
      setActionError(
        t("receipt.list.revoke_error", "That link did not come down. Try again."),
      );
    } finally {
      setRevokingId(null);
    }
  };

  // An audit list wants exact dates, not "today": the point is recognising a
  // link you forgot creating.
  const locale = localeForLanguage(
    normalizeEnabledLanguage(i18n.resolvedLanguage ?? i18n.language),
  );
  const formatDate = (value: string) =>
    new Intl.DateTimeFormat(locale, {
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(new Date(value));
  // The row carries the window as two frozen calendar days, so it is read in UTC
  // and spoken here. A run made in one language is still legible in the other.
  const formatWindow = (range: EvidenceReceipt["date_range"]) => {
    const day = (value: string) => {
      const parsed = new Date(`${value}T00:00:00Z`);
      return Number.isNaN(parsed.getTime())
        ? null
        : new Intl.DateTimeFormat(locale, {
            year: "numeric",
            month: "short",
            day: "numeric",
            timeZone: "UTC",
          }).format(parsed);
    };
    const start = day(range?.start ?? "");
    const end = day(range?.end ?? "");
    if (!start || !end) return null;
    return t("receipt.date_range", {
      start,
      end,
      defaultValue: "{{start}} to {{end}}",
    });
  };

  return (
    <AdaptivePanel
      title={t("receipt.list.title", "Shared links")}
      closeLabel={t("receipt.list.close", "Close shared links")}
      onClose={onClose}
      onBack={onBack}
      backLabel={backLabel}
      width="md"
      returnFocusRef={returnFocusRef}
    >
        <div className="px-5 py-4">
          <p className="text-[13px] leading-relaxed text-black/50 dark:text-white/50">
            {t(
              "receipt.list.intro",
              "Every link you have shared, with its frozen answers or test results.",
            )}
          </p>

          {actionError && (
            <p
              role="alert"
              className="mt-3 text-[12.5px] text-[#b94c55] dark:text-[#e7a2a8]"
            >
              {actionError}
            </p>
          )}

          {isLoading ? (
            <div className="flex items-center justify-center py-16">
              <Loader2 className="h-6 w-6 animate-spin text-black/20 dark:text-white/20" />
            </div>
          ) : loadFailed ? (
            <div className="flex flex-col items-center gap-3 py-14 text-center">
              <p className="text-[14px] text-black/50 dark:text-white/50">
                {t("receipt.list.load_error", "Your shared links did not load.")}
              </p>
              <button
                type="button"
                onClick={load}
                className="inline-flex min-h-11 items-center rounded-full border border-black/10 px-3.5 text-[12.5px] font-medium text-black/70 transition-colors hover:bg-black/[0.03] dark:border-white/10 dark:text-white/70 dark:hover:bg-white/[0.05]"
              >
                {t("receipt.list.retry", "Try again")}
              </button>
            </div>
          ) : receipts.length === 0 ? (
            <div className="flex flex-col items-center gap-4 py-16 text-center">
              <div className="flex h-16 w-16 items-center justify-center rounded-full bg-black/5 dark:bg-white/5">
                <Link2 className="h-8 w-8 text-black/20 dark:text-white/20" />
              </div>
              <p className="text-[14.5px] text-black/40 dark:text-white/40">
                {t("receipt.list.empty", "You have not shared anything yet.")}
              </p>
            </div>
          ) : (
            <ul className="mt-3 flex flex-col gap-3">
              {receipts.map((receipt) => {
                const isRevoked = Boolean(receipt.revoked_at);
                return (
                  <li
                    key={receipt.id}
                    className="rounded-[16px] border border-black/5 bg-black/[0.02] p-4 dark:border-white/5 dark:bg-white/[0.03]"
                  >
                    <p className="truncate text-[14.5px] font-medium text-black dark:text-white">
                      {receipt.title}
                    </p>
                    <p className="mt-0.5 truncate text-[12.5px] text-black/45 dark:text-white/45">
                      {[t(`receipt.kinds.${receipt.kind}`), receipt.symbols.join(", "), formatWindow(receipt.date_range)]
                        .filter(Boolean)
                        .join(" · ")}
                    </p>
                    <p className="mt-1 text-[12px] text-black/40 dark:text-white/40">
                      {isRevoked
                        ? t("receipt.list.revoked_on", {
                            date: formatDate(receipt.revoked_at as string),
                            defaultValue: "Taken down {{date}}",
                          })
                        : t("receipt.list.created_on", {
                            date: formatDate(receipt.created_at),
                            defaultValue: "Shared {{date}}",
                          })}
                    </p>
                    {isRevoked && receipt.revocation_reason === "source_deleted" && (
                      <p className="mt-1 text-[12px] leading-snug text-black/40 dark:text-white/40">
                        {t(
                          "receipt.list.revoked_by_source",
                          "Taken down on its own when you deleted the chat behind it.",
                        )}
                      </p>
                    )}
                    {!isRevoked && (
                      <div className="mt-3 flex flex-wrap items-center gap-2">
                        <button
                          type="button"
                          onClick={async () => {
                            const ok = await copyReceiptLink(receiptUrl(receipt));
                            setCopiedId(ok ? receipt.id : null);
                          }}
                          className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-black/10 px-3 text-[12px] font-medium text-black/70 transition-colors hover:bg-black/[0.04] dark:border-white/10 dark:text-white/70 dark:hover:bg-white/[0.06]"
                        >
                          {copiedId === receipt.id ? (
                            <Check className="h-3.5 w-3.5" />
                          ) : (
                            <Copy className="h-3.5 w-3.5" />
                          )}
                          {copiedId === receipt.id
                            ? t("receipt.owner.copied", "Copied")
                            : t("receipt.list.copy", "Copy link")}
                        </button>
                        <a
                          href={receipt.path}
                          target="_blank"
                          rel="noreferrer noopener"
                          className="inline-flex min-h-11 items-center gap-1.5 rounded-full border border-black/10 px-3 text-[12px] font-medium text-black/70 transition-colors hover:bg-black/[0.04] dark:border-white/10 dark:text-white/70 dark:hover:bg-white/[0.06]"
                        >
                          <ExternalLink className="h-3.5 w-3.5" />
                          {t("receipt.list.open", "Open it")}
                        </a>
                        <button
                          type="button"
                          disabled={revokingId === receipt.id}
                          onClick={() => {
                            if (confirmingId === receipt.id) {
                              void revoke(receipt);
                              return;
                            }
                            setConfirmingId(receipt.id);
                          }}
                          className="ml-auto inline-flex min-h-11 items-center rounded-full px-3 text-[12px] font-medium text-[#d66d75] transition-colors hover:bg-[#d66d75]/10 disabled:opacity-55"
                        >
                          {revokingId === receipt.id
                            ? t("receipt.list.revoking", "Taking it down...")
                            : confirmingId === receipt.id
                              ? t("receipt.list.confirm_revoke", "Sure?")
                              : t("receipt.list.revoke", "Take it down")}
                        </button>
                      </div>
                    )}
                  </li>
                );
              })}
            </ul>
          )}

          {nextCursor && (
            <div className="mt-3 flex justify-center">
              <button
                type="button"
                disabled={isLoadingMore}
                onClick={() => void loadMore()}
                className="inline-flex min-h-11 items-center rounded-full border border-black/10 px-3.5 text-[12.5px] font-medium text-black/70 transition-colors hover:bg-black/[0.03] disabled:opacity-55 dark:border-white/10 dark:text-white/70 dark:hover:bg-white/[0.05]"
              >
                {isLoadingMore
                  ? t("receipt.list.loading", "Loading your links...")
                  : t("receipt.list.load_more", "Show older links")}
              </button>
            </div>
          )}

          <p className="mt-5 text-[11.5px] leading-relaxed text-black/40 dark:text-white/40">
            {t(
              "receipt.list.cache_note",
              "The link dies on Cuadrao right away. Chat apps sometimes keep an old preview card in threads where it was already pasted, and Cuadrao cannot reach into those.",
            )}
          </p>
        </div>
    </AdaptivePanel>
  );
}
