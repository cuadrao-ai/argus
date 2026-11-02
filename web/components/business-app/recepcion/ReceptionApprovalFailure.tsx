"use client";

import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { quietButtonClass } from "../business-ui";
import type { ListoFailure } from "./reception-approval";
import styles from "./reception.module.css";

const REFUSAL_KEY: Readonly<Record<string, string>> = {
  duplicate_comprobante: "duplicate_comprobante",
  not_listo: "not_listo",
  stale_version: "stale_version",
};

/** Says which receipts were not approved and why. They stay in Listos, still selected. */
export default function ReceptionApprovalFailure({ failed, attempted, onRetry, onDismiss }: { failed: readonly ListoFailure[]; attempted: number; onRetry: () => void; onDismiss: () => void }) {
  const { t } = useTranslation();
  const word = (key: string, options = {}) => t(`business.reception_preview.placeholder.${key}`, options);
  const reference = failed.find(failure => failure.reference)?.reference;
  const why = ({ kind, code }: ListoFailure) => word(`refused.${kind === "unknown" ? "unknown" : REFUSAL_KEY[code ?? ""] ?? "other"}`);
  return <div className={styles.approvalFailure} role="alert" data-testid="reception-approval-failure">
    <p>{word("approve_failed", { count: failed.length, total: attempted })}{reference ? <span className="ml-2 inline-flex align-middle"><ReferenceCode reference={reference} /></span> : null}</p>
    <ul>{failed.map(failure => <li key={failure.target.rowId} data-testid="reception-approval-failed-row"><span>{failure.target.title}</span><span className={styles.approvalWhy}>{why(failure)}</span></li>)}</ul>
    <div className={styles.approvalFailureActions}>
      {failed.some(failure => failure.kind === "unknown") ? <button type="button" className={quietButtonClass} onClick={onRetry}>{t("common.retry")}</button> : null}
      <button type="button" className={quietButtonClass} onClick={onDismiss}>{t("common.close")}</button>
    </div>
  </div>;
}
