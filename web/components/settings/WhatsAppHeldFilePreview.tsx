"use client";

import Image from "next/image";
import { useCallback, useEffect, useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { FileText } from "lucide-react";
import { useTranslation } from "react-i18next";
import ReceiptImageZoom from "@/components/business-app/ReceiptImageZoom";
import { DelayedSourceWell } from "@/components/business-app/business-skeletons";
import { FOCUS_RING } from "@/components/business-app/foundation/presentation";
import { receiptFormatLabel } from "@/components/business-app/receipt-file";
import { readWhatsAppHeldPreview } from "@/lib/whatsapp-link-api";

type Preview = { link: string; url: string; blob: Blob } | { link: string; failed: true };

function useHeldPreview(link: string, requested: boolean) {
  const [result, setResult] = useState<Preview | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!requested) return;
    const abort = new AbortController();
    const reader = new FileReader();
    const fail = () => { if (!abort.signal.aborted) setResult({ link, failed: true }); };
    void readWhatsAppHeldPreview(link, abort.signal).then(blob => {
      if (abort.signal.aborted) return;
      if (blob.type === "application/pdf") {
        setResult({ link, url: "", blob });
        return;
      }
      reader.onload = () => {
        if (!abort.signal.aborted) setResult({ link, url: String(reader.result), blob });
      };
      reader.onerror = fail;
      reader.readAsDataURL(blob);
    }).catch(fail);
    return () => {
      abort.abort();
      if (reader.readyState === FileReader.LOADING) reader.abort();
    };
  }, [link, requested, attempt]);
  return {
    result: result?.link === link ? result : null,
    retry: () => { setResult(null); setAttempt(value => value + 1); },
  };
}

export function WhatsAppHeldFilePreview({ id, mediaType, previewUrl, reading, children }: {
  id: string; mediaType: string; previewUrl: string; reading?: boolean; children: ReactNode;
}) {
  const { t } = useTranslation();
  const thumbnail = useRef<HTMLButtonElement>(null);
  const viewerHost = useRef<HTMLDivElement>(null);
  const [open, setOpen] = useState(false);
  const titleId = useId();
  const pdf = mediaType === "application/pdf";
  const [requested, setRequested] = useState(false);
  useEffect(() => {
    if (requested || pdf || !thumbnail.current || typeof IntersectionObserver === "undefined") return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) setRequested(true);
    }, { rootMargin: "120px" });
    observer.observe(thumbnail.current);
    return () => observer.disconnect();
  }, [requested, pdf]);
  const { result, retry } = useHeldPreview(previewUrl, requested);
  const ready = result && "blob" in result ? result : null;
  const fullScreenLabel = t("business.dossier.viewer.full_screen");
  const fullScreenControl = useCallback(() =>
    Array.from(viewerHost.current?.querySelectorAll("button") ?? []).find(button => button.getAttribute("aria-label") === fullScreenLabel),
  [fullScreenLabel]);
  useLayoutEffect(() => {
    if (!open || !ready || document.activeElement !== thumbnail.current) return;
    fullScreenControl()?.click();
  }, [open, ready, fullScreenControl]);
  const focusReturned = () => {
    if (fullScreenControl()) setOpen(false);
  };

  const show = () => {
    thumbnail.current?.focus();
    setRequested(true);
    setOpen(true);
  };
  return <div className="flex items-start gap-3">
    <button ref={thumbnail} type="button" aria-label={t("command_palette.preview")} aria-describedby={titleId} aria-haspopup="dialog" onClick={show} onFocus={focusReturned}
      className={`relative grid h-[60px] w-12 shrink-0 place-items-center overflow-hidden rounded-item border border-[var(--surface-divider)] bg-white ${FOCUS_RING} ${reading ? "motion-safe:animate-pulse" : ""}`}>
      {pdf ? <svg aria-hidden="true" viewBox="0 0 48 60" width="48" height="60" fill="none">
        <path stroke="#56635e" strokeWidth="3" d="M8 10.5h18"/>
        <path stroke="#c9cfc9" strokeWidth="2" d="M8 18h32M8 23h32M8 28h24M8 33h32"/>
      </svg> : ready ? <Image unoptimized src={ready.url} alt="" width={48} height={60} className="h-full w-full object-cover" />
        : <FileText size={32} strokeWidth={1.25} className="text-[#85918c]" aria-hidden="true" />}
      {pdf && <span aria-hidden="true" className="absolute bottom-1 left-1 rounded-sm bg-[#172b26] px-1 text-[9px] leading-4 font-bold text-white">{receiptFormatLabel(mediaType)}</span>}
    </button>
    <button type="button" id={titleId} aria-hidden="true" tabIndex={-1} onClick={show} className="min-w-0 flex-1 text-left">{children}</button>
    {open && (ready ? <div ref={viewerHost} hidden>
      <ReceiptImageZoom sourceId={id} alt={t("business.review.source")} src={ready.url} blob={ready.blob} pdf={pdf} />
    </div> : result && "failed" in result ? <div>
      <p role="alert">{t("business.review.source_error")}</p>
      <button type="button" onClick={() => { show(); retry(); }}>{t("business.dossier.retry_source")}</button>
    </div> : <DelayedSourceWell />)}
  </div>;
}
