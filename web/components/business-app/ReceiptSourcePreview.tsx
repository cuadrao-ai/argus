"use client";

import Image from "next/image";
import { useEffect, useState } from "react";
import { Download, RotateCcw } from "lucide-react";
import { useTranslation } from "react-i18next";
import type { ReceiptSummary } from "@/lib/business-api";
import { useBusiness } from "./BusinessWorkspace";
import { formatTimestamp } from "./business-format";
import { cardClass, secondaryButtonClass, useChannelLabel } from "./business-ui";

export default function ReceiptSourcePreview({ detail }: { detail: Pick<ReceiptSummary, "id" | "media_type" | "filename" | "received_at" | "channel" | "email_delivery_ids"> }) {
  const { t, i18n } = useTranslation();
  const { source, openPanel } = useBusiness();
  const channelLabel = useChannelLabel();
  const deliveries = detail.email_delivery_ids?.length ?? 0;
  // The API lists deliveries earliest first; the first one is where the file first arrived by email.
  const firstEmail = detail.email_delivery_ids?.[0];
  const [state, setState] = useState<{ kind: "loading" } | { kind: "ready"; url: string } | { kind: "failed" }>({ kind: "loading" });
  const [expanded, setExpanded] = useState(false);
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    let cancelled = false;
    source.receiptSource(detail.id)
      .then((blob) => new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result));
        reader.onerror = () => reject(reader.error);
        reader.readAsDataURL(blob);
      }))
      .then((url) => { if (!cancelled) setState({ kind: "ready", url }); })
      .catch(() => { if (!cancelled) setState({ kind: "failed" }); });
    return () => { cancelled = true; };
  }, [detail.id, source, retry]);

  return (
    <figure className={`${cardClass} p-3`} data-testid="receipt-original-source">
      <button type="button" aria-expanded={expanded} onClick={() => setExpanded((value) => !value)} className="flex min-h-11 w-full items-center gap-3 rounded-lg text-left text-[14px] font-medium text-black/80 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--cuadrao-green)] dark:text-white/85 desktop:hidden">
        {!expanded && state.kind === "ready" && (detail.media_type.startsWith("image/") || source.mode === "fixture") ? <Image unoptimized src={state.url} width={64} height={80} alt="" className="h-20 w-16 rounded-md object-contain" /> : null}
        {expanded ? t("common.close", "Close") : t("business.review.source", "Original receipt")}
      </button>
      <div className={`${expanded ? "mt-3 flex desktop:mt-0" : "hidden desktop:flex"} min-h-[200px] items-center justify-center overflow-hidden rounded-[14px] bg-black/[0.03] dark:bg-white/[0.04] desktop:min-h-[280px]`}>
        {state.kind === "failed" ? (
          <div className="p-5 text-center">
            <p role="alert" className="text-[14px] text-black/65 dark:text-white/65">{t("business.review.source_error", "We couldn't open the original receipt with your current access.")}</p>
            <button type="button" className={`${secondaryButtonClass} mt-3`} onClick={() => { setState({ kind: "loading" }); setRetry((value) => value + 1); }}>
              <RotateCcw className="h-4 w-4" aria-hidden="true" />{t("business.dossier.retry_source", "Try opening again")}
            </button>
          </div>
        ) : state.kind === "loading" ? (
          <span role="status" className="text-[14px] text-black/55 dark:text-white/55">{t("common.loading", "Loading")}</span>
        ) : detail.media_type === "application/pdf" && source.mode === "live" ? (
          <iframe title={t("business.review.source", "Original receipt")} src={state.url} className="h-[480px] w-full" />
        ) : detail.media_type.startsWith("image/") || source.mode === "fixture" ? (
          <Image unoptimized src={state.url} width={640} height={900} alt={t("business.review.source", "Original receipt")} className="max-h-[300px] w-auto object-contain desktop:max-h-[520px]" />
        ) : (
          <p className="p-5 text-[14px] text-black/65 dark:text-white/65">{t("business.dossier.download_source", "Download the original to read this file.")}</p>
        )}
      </div>
      <figcaption className={`${expanded ? "" : "hidden desktop:block"} mt-3 px-1 text-[13px] text-black/60 dark:text-white/60`}>
        <div className="flex items-center justify-between gap-2">
          <span className="min-w-0 break-all">{detail.filename ?? t("business.review.source", "Original receipt")}</span>
          {state.kind === "ready" ? <a href={state.url} download={detail.filename ?? "receipt"} className="flex min-h-11 shrink-0 items-center gap-1.5 rounded-full px-3 font-medium hover:bg-black/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:hover:bg-white/5 dark:focus-visible:ring-white/20"><Download className="h-4 w-4" aria-hidden="true" />{t("business.review.download", "Download")}</a> : null}
        </div>
        <p data-testid="receipt-source-channel">
          {channelLabel(detail.channel)}
          {detail.channel === "email" && firstEmail ? <>{" · "}<button type="button" className="font-medium underline underline-offset-4" onClick={() => openPanel({ kind: "inbox", emailId: firstEmail })}>{t("business.dossier.see_first_email", "See the first email")}</button></> : null}
        </p>
        {deliveries > 1 ? <p className="mt-1" data-testid="receipt-email-times">{t("business.dossier.email_times", { count: deliveries, defaultValue: "This file arrived {{count}} times by email." })}{firstEmail && detail.channel !== "email" ? <>{" "}<button type="button" className="font-medium underline underline-offset-4" onClick={() => openPanel({ kind: "inbox", emailId: firstEmail })}>{t("business.dossier.see_first_email", "See the first email")}</button></> : null}</p> : null}
        <p className="mt-1">{t("business.dossier.received", "Received {{time}}", { time: formatTimestamp(detail.received_at, i18n.resolvedLanguage ?? "en") })}</p>
      </figcaption>
    </figure>
  );
}
