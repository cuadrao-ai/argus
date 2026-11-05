"use client";

import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import type { ReviewFlagCode } from "@/lib/business-dossier";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

/**
 * The step a confirm flag puts before approval. Fixing is the primary way out
 * and approving anyway the deliberate second one; Escape, back and the
 * backdrop close the step without approving.
 */
function ReviewFlagConfirmSurface({ codes, onFix, onApproveAnyway, onClose }: {
  codes: readonly ReviewFlagCode[];
  onFix: () => void;
  onApproveAnyway: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const overlayId = useId();
  const ids = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const fixRef = useRef<HTMLButtonElement>(null);
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, initialFocusRef: fixRef, onDismiss: onClose });
  return <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
    <button type="button" tabIndex={-1} aria-label={t("common.cancel")} onClick={onClose} className="absolute inset-0" />
    <div ref={panelRef} role="alertdialog" aria-modal="true" data-testid="review-flag-confirm" aria-labelledby={codes.map((code) => `${ids}-${code}-title`).join(" ")} aria-describedby={[...codes.map((code) => `${ids}-${code}-text`), `${ids}-export`].join(" ")} className="relative max-h-[calc(100dvh-2rem)] w-full max-w-sm overflow-y-auto rounded-surface border border-black/10 bg-white p-5 dark:border-white/10 dark:bg-[#1f2225]">
      {codes.map((code) => <div key={code} data-flag={code} className="mb-4">
        <h2 id={`${ids}-${code}-title`} className="font-display text-[17px] font-medium text-black dark:text-white">{t(`business.dossier.review_flag.${code}.title`)}</h2>
        <p id={`${ids}-${code}-text`} className="mt-2 text-[14px] leading-relaxed text-black/75 dark:text-white/75">{t(`business.dossier.review_flag.${code}.text`)}</p>
      </div>)}
      <p id={`${ids}-export`} className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{t("business.dossier.review_flag.export_blocked")}</p>
      <div className="mt-5 flex flex-col-reverse gap-2 sm:flex-row sm:justify-end">
        <button type="button" className={secondaryButtonClass} onClick={onApproveAnyway}>{t("business.dossier.review_flag.approve_anyway")}</button>
        <button ref={fixRef} type="button" className={primaryButtonClass} onClick={onFix}>{t("business.dossier.review_flag.fix")}</button>
      </div>
    </div>
  </div>;
}

export default withViewportPortal(ReviewFlagConfirmSurface);
