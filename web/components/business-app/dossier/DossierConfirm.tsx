"use client";

import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import type { DossierProblem } from "../dossier-attention";
import styles from "./dossier.module.css";

export default function DossierConfirm({ problems, onFix, onProblem, onAcceptAnyway, onClose }: {
  problems: readonly DossierProblem[];
  onFix: () => void;
  onProblem: (problem: DossierProblem) => void;
  onAcceptAnyway?: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const count = problems.length;
  const words = "business.dossier.confirm.placeholder";
  return <ConfirmDialog
    isOpen
    tone="primary"
    testId="dossier-confirm"
    title={t(`${words}.title`, { count })}
    description={t(`${words}.subtitle`, { count })}
    cancelLabel={t("common.cancel")}
    onCancel={onClose}
    confirmLabel={t("business.dossier.confirm.fix")}
    onConfirm={onFix}
    secondaryAction={onAcceptAnyway ? { label: t("business.dossier.confirm.accept_anyway"), onClick: onAcceptAnyway } : null}
    details={<ul className={`${styles.scope} ${styles.confirmList}`}>
      {problems.map(problem => <li key={problem.key} data-problem={problem.key}>
        <div>
          <strong>{problem.where}</strong>
          <p>{problem.amountComparison ? <>
            {problem.amountComparison.totals && `${problem.amountComparison.totals} · `}
            <span className="whitespace-nowrap">{problem.amountComparison.difference}</span>
          </> : problem.reason === "review_flag" ? problem.text : [problem.title, problem.text].filter(Boolean).join(". ")}</p>
        </div>
        <button type="button" className={styles.link} onClick={() => onProblem(problem)} aria-label={`${t(`${words}.go`)} · ${problem.where}`}>{t(`${words}.go`)}</button>
      </li>)}
    </ul>}
  />;
}
