import Image from "next/image";
import type { ReactNode } from "react";
import styles from "./invoicing-preview.module.css";

export function invoiceEmptyKind(total: number, stageCount: number, resultCount: number) {
  return resultCount > 0 ? null : total === 0 ? "first" : stageCount === 0 ? "stage" : "filtered";
}

export default function WorkspaceEmptyState({ title, description, action, compact = false, art = "invoice" }: { title: string; description?: string; action?: ReactNode; compact?: boolean; art?: "invoice" | "schedule" | "customer" }) {
  const src = art === "schedule" ? "/images/invoicing/schedule-calendar.png" : art === "customer" ? "/images/invoicing/customer-directory.png" : "/images/invoicing/first-invoice.png";
  return <div className={styles.workspaceEmpty} data-compact={compact}>
    <Image src={src} alt="" width={compact ? 88 : 144} height={compact ? 88 : 144} />
    <h3>{title}</h3>{description ? <p>{description}</p> : null}{action}
  </div>;
}
