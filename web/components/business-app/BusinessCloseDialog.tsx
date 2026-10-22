"use client";

import { useId, useRef, useState, type ReactNode, type RefObject } from "react";
import spanish from "@/public/locales/es-419/common.json";
import { FormField } from "@/components/ui/FormField";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { businessDeadlineParts } from "@/lib/business-lifecycle-api";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { resolveLanguage } from "@/lib/language-features";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { dangerButtonClass, dangerConfirmButtonClass, secondaryButtonClass } from "./business-ui";

export const businessCloseCopyEs = {
  title: spanish.business.lifecycle.close.title,
  warning: spanish.business.lifecycle.close.warning,
  consequences: spanish.business.lifecycle.close.consequences,
  confirmation: spanish.business.lifecycle.name_confirmation,
  download: spanish.business.lifecycle.close.download,
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
  preview?: Pick<OwnedBusiness, "member_count" | "reopen_until">;
  onConfirm: (confirmation: string) => void;
};

function CloseConfirmationSurface({ businessName, copy, state, preview, onConfirm, onBack, returnFocusRef }: CloseProps & {
  onBack: () => void;
  returnFocusRef: RefObject<HTMLButtonElement | null>;
}) {
  const { t, i18n } = useTranslation();
  const overlayId = useId();
  const titleId = useId();
  const inputId = useId();
  const descriptionId = useId();
  const errorId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [confirmation, setConfirmation] = useState("");
  const submitting = state.kind === "submitting";
  const cancel = () => { if (!submitting) onBack(); };
  const matches = businessName.length > 0 && confirmation === businessName;
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, initialFocusRef: inputRef, returnFocusRef, onDismiss: cancel, canDismiss: () => !submitting });
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});

  const countKey = preview?.member_count === 0 ? "zero" : preview?.member_count === 1 ? "one" : "other";

  return <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
    <button type="button" tabIndex={-1} aria-label={copy.cancel} disabled={submitting} onClick={cancel} className="absolute inset-0" />
    <div ref={panelRef} role="alertdialog" aria-modal="true" aria-labelledby={titleId} aria-describedby={descriptionId} aria-busy={submitting} className="relative max-h-[calc(100dvh-2rem)] w-full max-w-sm overflow-y-auto rounded-surface border border-black/10 bg-white p-5 dark:border-white/10 dark:bg-[#1f2225]">
      <h2 id={titleId} className="font-display text-[17px] font-medium text-black dark:text-white">{t("business.lifecycle.close_alert_title", { businessName })}</h2>
      <div id={descriptionId} className="mt-3 space-y-2 text-[14px] leading-relaxed text-black/75 dark:text-white/75">
        <p>{copy.consequences}</p>
        {preview ? <>
          <p>{t(`business.lifecycle.close_preview.member_count_${countKey}`, { count: preview.member_count })}</p>
          <p>{t("business.lifecycle.close_preview.reopen_until", businessDeadlineParts(preview.reopen_until, locale))}</p>
        </> : null}
      </div>
      <form className="mt-5 space-y-5" onSubmit={event => { event.preventDefault(); if (matches && !submitting) onConfirm(confirmation); }}>
        <div>
          <p className="mb-2 break-words text-[16px] font-semibold">{businessName}</p>
          <FormField ref={inputRef} id={inputId} label={copy.confirmation} value={confirmation} onChange={event => setConfirmation(event.target.value)} disabled={submitting} error={state.kind === "error" && state.field ? state.message : undefined} autoComplete="off" autoCapitalize="off" spellCheck={false} />
        </div>
        {state.kind === "error" ? <div id={errorId} role="alert" className="space-y-2 text-[14px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">{!state.field ? <p>{state.message}</p> : null}{state.reference ? <ReferenceCode reference={state.reference} /> : null}</div> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" onClick={cancel} disabled={submitting} className={secondaryButtonClass}>{copy.cancel}</button>
          <button type="submit" disabled={!matches || submitting} className={dangerConfirmButtonClass}>{copy.close}</button>
        </div>
      </form>
    </div>
  </div>;
}

const CloseConfirmation = withViewportPortal(CloseConfirmationSurface);

export default function BusinessCloseDialog({ exportControl, onCancel, ...props }: CloseProps & { exportControl: ReactNode; onCancel: () => void }) {
  const [phase, setPhase] = useState<"download" | "confirm">("download");
  const warningRef = useRef<HTMLParagraphElement>(null);
  const continueRef = useRef<HTMLButtonElement>(null);
  if (phase === "confirm") return <CloseConfirmation {...props} onBack={() => setPhase("download")} returnFocusRef={continueRef} />;
  return <AdaptivePanel title={props.copy.title} closeLabel={props.copy.cancel} onClose={onCancel} width="md" initialFocusRef={warningRef}>
    <div className="space-y-5 p-5">
      <p ref={warningRef} tabIndex={-1} className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{props.copy.warning}</p>
      {exportControl}
      <p className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{props.copy.consequences}</p>
      <div className="flex justify-end"><button ref={continueRef} type="button" className={dangerButtonClass} onClick={() => setPhase("confirm")}>{props.copy.close}</button></div>
    </div>
  </AdaptivePanel>;
}
