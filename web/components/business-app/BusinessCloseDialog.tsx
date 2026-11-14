"use client";

import { useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Check, ChevronLeft, Download, Loader2, TriangleAlert } from "lucide-react";
import spanish from "@/public/locales/es-419/common.json";
import { FormField } from "@/components/ui/FormField";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { businessDeadlineParts } from "@/lib/business-lifecycle-api";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BottomSheet from "@/components/ui/BottomSheet";
import CenteredDialog from "@/components/ui/CenteredDialog";
import { resolveLanguage } from "@/lib/language-features";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { formatDaySpan } from "./business-format";
import { dangerConfirmButtonClass, primaryButtonClass, quietButtonClass, secondaryButtonClass } from "./business-ui";
import type { CloseDownload, CloseDownloads } from "./useBusinessCloseDownloads";

export type { CloseDownload, CloseDownloads } from "./useBusinessCloseDownloads";

export const businessCloseCopyEs = {
  title: spanish.business.lifecycle.close.title,
  warning: spanish.business.lifecycle.close.warning,
  consequences: spanish.business.lifecycle.close.consequences,
  confirmation: spanish.business.lifecycle.name_confirmation,
  download: spanish.business.lifecycle.close.download,
  continue: spanish.business.lifecycle.close.continue,
  continueWithout: spanish.business.lifecycle.close.continue_without,
  close: spanish.business.lifecycle.close.action,
  cancel: spanish.common.cancel,
};

export function useBusinessCloseCopy() {
  const { t } = useTranslation();
  return {
    title: t("business.lifecycle.close.title", businessCloseCopyEs.title),
    warning: t("business.lifecycle.close.warning", businessCloseCopyEs.warning),
    consequences: t("business.lifecycle.close.consequences", businessCloseCopyEs.consequences),
    confirmation: t("business.lifecycle.name_confirmation", businessCloseCopyEs.confirmation),
    download: t("business.lifecycle.close.download", businessCloseCopyEs.download),
    continue: t("business.lifecycle.close.continue", businessCloseCopyEs.continue),
    continueWithout: t("business.lifecycle.close.continue_without", businessCloseCopyEs.continueWithout),
    close: t("business.lifecycle.close.action", businessCloseCopyEs.close),
    cancel: t("common.cancel", businessCloseCopyEs.cancel),
  };
}

export type BusinessCloseState =
  | { kind: "idle" }
  | { kind: "submitting" }
  | { kind: "error"; message: string; reference?: string | null; field?: "confirmation" };

type BusinessCloseCopy = { [Key in keyof typeof businessCloseCopyEs]: string };
type CloseProps = {
  businessName: string;
  copy: BusinessCloseCopy;
  state: BusinessCloseState;
  preview: Pick<OwnedBusiness, "member_count" | "reopen_until">;
  downloads: CloseDownloads;
  onConfirm: (confirmation: string) => void;
  onCancel: () => void;
};

const mutedTextClass = "text-[#56635e] dark:text-white/70";

/**
 * Closing a Business is one short task: a centered dialog on desktop and the
 * shared bottom sheet below the desktop stop, as Exportar registros.
 */
export function BusinessCloseShell({ title, closeLabel, onClose, locked = false, footer, children }: { title: string; closeLabel: string; onClose: () => void; locked?: boolean; footer?: ReactNode; children: ReactNode }) {
  const { isBelowDesktop } = useResponsiveLayout();
  const close = () => { if (!locked) onClose(); };
  if (isBelowDesktop) return <BottomSheet isOpen onClose={close} dismissible={!locked} title={title} closeLabel={closeLabel} snaps={["full"]} initialSnap="full" footer={footer}><div className="pb-5 pt-1">{children}</div></BottomSheet>;
  return <CenteredDialog title={title} closeLabel={closeLabel} onClose={close} footer={footer} testId="business-close-dialog"><div className="px-6 pb-5 pt-1">{children}</div></CenteredDialog>;
}

function PeriodRow({ item, busy, onStart }: { item: CloseDownload; busy: boolean; onStart: () => void }) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const span = formatDaySpan(item.start, item.end, locale);
  const period = span.to === null ? span.from : t("business.period.range", { from: span.from, to: span.to, defaultValue: "{{from}} – {{to}}" });
  // Counts are the server's, said in the reader's number format.
  const counted = (key: "records" | "originals", count: number) => t(`business.lifecycle.export.${key}`, { count, n: count.toLocaleString(locale) });
  const action = t(item.status === "failed" ? "common.retry" : "business.lifecycle.export.download");
  return (
    <li data-testid="business-close-period" data-status={item.status} className="flex min-h-14 items-center gap-3 rounded-item border border-black/15 py-2 pl-3 pr-2 dark:border-white/20">
      <div className="min-w-0 flex-1 text-[14px]">
        <p className="flex flex-wrap items-center gap-x-2 font-medium">
          <span>{period}</span>
          {item.status === "downloaded" ? <span className="inline-flex items-center gap-1 text-[13px] font-normal text-[var(--cuadrao-green)]"><Check className="h-3.5 w-3.5" aria-hidden="true" />{t("business.lifecycle.export.downloaded")}</span> : null}
        </p>
        <p className="tabular-nums text-black/60 dark:text-white/60">{counted("records", item.record_count)} · {counted("originals", item.original_count)}</p>
      </div>
      {item.status === "loading" ? <span role="status" aria-label={t("business.export.preparing")} className="flex h-11 w-11 shrink-0 items-center justify-center"><Loader2 className={`h-5 w-5 animate-spin motion-reduce:animate-none ${mutedTextClass}`} aria-hidden="true" /></span>
        : item.status === "downloaded" ? <button type="button" disabled={busy} aria-label={`${t("business.transactions.reporting.export.download_again")}: ${period}`} onClick={onStart} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40 dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"><Download className="h-5 w-5" aria-hidden="true" /></button>
        : <button type="button" disabled={busy} aria-label={`${action}: ${period}`} onClick={onStart} className={`${quietButtonClass} shrink-0 px-2`}>{action}</button>}
    </li>
  );
}

/**
 * Two steps in one dialog: download what the law asks the Business to keep,
 * one server period at a time, then the red confirm that closes it.
 */
export default function BusinessCloseDialog({ businessName, copy, state, preview, downloads, onConfirm, onCancel }: CloseProps) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [phase, setPhase] = useState<"download" | "confirm">("download");
  const [confirmation, setConfirmation] = useState("");
  const inputId = useId();
  const inputRef = useRef<HTMLInputElement>(null);
  const nextRef = useRef<HTMLButtonElement>(null);
  const moved = useRef(false);
  // A step change keeps the reader's place: the name field going in, the next step coming back.
  useEffect(() => {
    if (moved.current) (phase === "confirm" ? inputRef : nextRef).current?.focus();
  }, [phase]);
  const go = (next: typeof phase) => { moved.current = true; setPhase(next); };

  const { items } = downloads;
  const busy = items.some((item) => item.status === "loading");
  const failed = items.some((item) => item.status === "failed");
  const remaining = items.filter((item) => item.status !== "downloaded").length;
  const submitting = state.kind === "submitting";
  const matches = businessName.length > 0 && confirmation === businessName;
  const submit = () => { if (matches && !submitting) onConfirm(confirmation); };

  if (phase === "confirm") {
    const countKey = preview.member_count === 0 ? "zero" : preview.member_count === 1 ? "one" : "other";
    const footer = (
      <div className="flex flex-wrap justify-end gap-2">
        <button type="button" onClick={() => go("download")} disabled={submitting} className={secondaryButtonClass}>{copy.cancel}</button>
        <button type="button" onClick={submit} disabled={!matches || submitting} aria-busy={submitting || undefined} className={dangerConfirmButtonClass}>{copy.close}</button>
      </div>
    );
    return (
      <BusinessCloseShell title={t("business.lifecycle.close_alert_title", { businessName })} closeLabel={copy.cancel} onClose={onCancel} locked={submitting} footer={footer}>
        <button type="button" disabled={submitting} onClick={() => go("download")} className="-ml-1 mb-1 flex min-h-11 items-center gap-1.5 rounded-full px-1 text-[14px] text-[#56635e] hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40 dark:text-white/70 dark:hover:text-white">
          <ChevronLeft className="h-4 w-4" aria-hidden="true" />{copy.title}
        </button>
        <div className="space-y-2 text-[14px] leading-relaxed text-black/75 dark:text-white/75" aria-busy={submitting || undefined}>
          {remaining ? <p data-testid="business-close-missing" className="flex items-start gap-2 text-[#172b26] dark:text-white"><TriangleAlert className="mt-0.5 h-4 w-4 shrink-0 text-amber-600 dark:text-amber-400" aria-hidden="true" /><span>{t("business.lifecycle.close.missing", { count: remaining })}</span></p> : null}
          <p>{copy.consequences}</p>
          <p>{t(`business.lifecycle.close_preview.member_count_${countKey}`, { count: preview.member_count })}</p>
          <p>{t("business.lifecycle.close_preview.reopen_until", businessDeadlineParts(preview.reopen_until, locale))}</p>
        </div>
        <form className="mt-5" onSubmit={(event) => { event.preventDefault(); submit(); }}>
          <p className="mb-2 break-words text-[16px] font-semibold">{businessName}</p>
          <FormField ref={inputRef} id={inputId} label={copy.confirmation} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={submitting} error={state.kind === "error" && state.field ? state.message : undefined} autoComplete="off" autoCapitalize="off" spellCheck={false} />
        </form>
        {state.kind === "error" ? <div role="alert" className="mt-3 space-y-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">{!state.field ? <p>{state.message}</p> : null}{state.reference ? <ReferenceCode reference={state.reference} /> : null}</div> : null}
      </BusinessCloseShell>
    );
  }

  const footer = (
    <div className="space-y-2">
      {failed ? <p role="alert" className="text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{t("business.lifecycle.export.failed")}</p> : null}
      {items.length && !remaining ? <p role="status" className={`text-[13px] ${mutedTextClass}`}>{t("business.lifecycle.export.complete")}</p> : null}
      {remaining ? (
        <div className="flex flex-col-reverse gap-x-3 gap-y-1 sm:flex-row sm:items-center sm:justify-between">
          <button type="button" disabled={busy} onClick={() => go("confirm")} className={`${quietButtonClass} justify-center`}>{copy.continueWithout}</button>
          <button ref={nextRef} type="button" disabled={busy} aria-busy={busy || undefined} onClick={() => downloads.start()} className={primaryButtonClass}>
            {busy ? <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" /> : null}
            {busy ? t("business.lifecycle.export.preparing") : copy.download}
          </button>
        </div>
      ) : <div className="flex justify-end"><button ref={nextRef} type="button" onClick={() => go("confirm")} className={`${primaryButtonClass} w-full sm:w-auto`}>{copy.continue}</button></div>}
    </div>
  );
  return (
    <BusinessCloseShell title={copy.title} closeLabel={copy.cancel} onClose={onCancel} footer={footer}>
      <p className={`mb-4 text-[14px] leading-relaxed ${mutedTextClass}`}>{copy.warning}</p>
      {items.length ? <>
        <ul className="space-y-2" aria-busy={busy || undefined}>
          {items.map((item) => <PeriodRow key={item.key} item={item} busy={busy} onStart={() => downloads.start(item.key)} />)}
        </ul>
        <p className={`mt-3 text-[13px] ${mutedTextClass}`}>{t("business.lifecycle.export.package")}</p>
      </> : <p className="text-[14px]">{t("business.lifecycle.export.empty")}</p>}
    </BusinessCloseShell>
  );
}
