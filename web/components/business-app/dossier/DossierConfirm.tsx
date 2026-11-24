"use client";

import { useId, useRef } from "react";
import { useTranslation } from "react-i18next";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import { primaryButtonClass, secondaryButtonClass } from "../business-ui";
import type { DossierProblem } from "../dossier-attention";
import styles from "./dossier.module.css";

/**
 * The step before accepting a record that is not Listos. It lists every reason.
 * Accepting anyway is offered when the server says every gap is confirmable.
 * Escape, back and the backdrop close the step without accepting.
 */
function DossierConfirmSurface({ problems, onFix, onAcceptAnyway, onClose }: {
  problems: readonly Pick<DossierProblem, "key" | "title" | "text">[];
  onFix: () => void;
  onAcceptAnyway?: () => void;
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
    <div ref={panelRef} role="alertdialog" aria-modal="true" data-testid="dossier-confirm" aria-labelledby={`${ids}-title`} aria-describedby={`${ids}-list`} className="relative max-h-[calc(100dvh-2rem)] w-full max-w-[420px] overflow-y-auto rounded-surface border border-black/10 bg-[#FFFEFA] p-6 dark:border-white/10 dark:bg-[#1f2225]">
      <h2 id={`${ids}-title`} className="mb-2 font-display text-[18px] font-semibold text-[#172b26] dark:text-white">{problems.length === 1 ? problems[0].title : t("business.dossier.problems.count", { count: problems.length })}</h2>
      <ul id={`${ids}-list`} className={styles.confirmList}>
        {problems.map((problem) => <li key={problem.key} data-problem={problem.key}>{problems.length > 1 ? <strong>{problem.title}{problem.text ? "." : ""}</strong> : null}{problem.text ? `${problems.length > 1 ? " " : ""}${problem.text}` : null}</li>)}
      </ul>
      <div className="mt-4 flex flex-col-reverse gap-2.5 sm:flex-row sm:justify-end">
        {onAcceptAnyway ? <button type="button" className={secondaryButtonClass} onClick={onAcceptAnyway}>{t("business.dossier.confirm.accept_anyway")}</button> : null}
        <button ref={fixRef} type="button" className={primaryButtonClass} onClick={onFix}>{t("business.dossier.confirm.fix")}</button>
      </div>
    </div>
  </div>;
}

export default withViewportPortal(DossierConfirmSurface);
