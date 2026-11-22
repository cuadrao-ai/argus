"use client";

import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { primaryButtonClass, secondaryButtonClass } from "../business-ui";
import styles from "./dossier.module.css";

/** One thing the confirm names: a reason the record is not Listos. */
export type ConfirmProblem = { key: string; title: string; text: string };

/**
 * The step before accepting a record that is not Listos. It lists every reason.
 * Fixing is the primary way out and accepting anyway the deliberate second one.
 * Escape, back and the backdrop close the step without accepting.
 */
function DossierConfirmSurface({ problems, onFix, onAcceptAnyway, onClose }: {
  problems: readonly ConfirmProblem[];
  onFix: () => void;
  onAcceptAnyway: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const overlayId = useId();
  const ids = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const fixRef = useRef<HTMLButtonElement>(null);
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, initialFocusRef: fixRef, onDismiss: onClose });
  return <div className={`${styles.scope} fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60`}>
    <button type="button" tabIndex={-1} aria-label={t("common.cancel")} onClick={onClose} className="absolute inset-0" />
    <div ref={panelRef} role="alertdialog" aria-modal="true" data-testid="review-flag-confirm" aria-labelledby={`${ids}-title`} aria-describedby={`${ids}-list ${ids}-export`} className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[420px] overflow-y-auto rounded-surface border border-black/10 bg-[#FFFEFA] p-6 dark:border-white/10 dark:bg-[#1f2225]">
      <h2 id={`${ids}-title`} className="mb-2 font-display text-[18px] font-semibold text-[#172b26] dark:text-white">{problems.length === 1 ? problems[0].title : t("business.dossier.problems.count", { count: problems.length })}</h2>
      <ul id={`${ids}-list`} className={styles.confirmList}>
        {problems.map((problem) => <li key={problem.key} data-problem={problem.key}><strong>{problem.title}.</strong> {problem.text}</li>)}
      </ul>
      <p id={`${ids}-export`} className={styles.confirmNote}>{t("business.dossier.review_flag.export_blocked")}</p>
      <div className="mt-4 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
        <button type="button" className={secondaryButtonClass} onClick={onAcceptAnyway}>{t("business.dossier.review_flag.approve_anyway")}</button>
        <button ref={fixRef} type="button" className={primaryButtonClass} onClick={onFix}>{t("business.dossier.review_flag.fix")}</button>
      </div>
    </div>
  </div>;
}

export default withViewportPortal(DossierConfirmSurface);
