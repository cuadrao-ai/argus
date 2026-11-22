"use client";

import { useSyncExternalStore } from "react";
import { useTranslation } from "react-i18next";
import { enteredIn } from "@/lib/business-grant";
import type { IntakeTarget, ReceiptUploadQueue } from "./receipt-upload-queue";
import { uploadBatchView, uploadSummaryText } from "./receipt-upload-view";
import styles from "./receipt-intake.module.css";

/**
 * The closed upload panel, as one chip in the top bar: how far this Business's batch is, then how it ended.
 * It reads the same queue and the same counts as the panel, and opens the panel again.
 */
export default function ReceiptUploadChip({ queue, grant, onOpen }: { queue: ReceiptUploadQueue; grant: string | null; onOpen: (target: IntakeTarget) => void }) {
  const { t } = useTranslation();
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter(enteredIn(grant));
  if (!entries.length) return null;
  const batch = uploadBatchView(entries, queue.retryWaiting);
  const target = [...batch.active, ...batch.waiting, ...batch.attention, ...entries][0].target;
  return (
    <button type="button" data-testid="receipt-upload-chip" data-busy={batch.busy ? "true" : "false"} onClick={() => onOpen(target)} className="inline-flex h-10 items-center gap-2 whitespace-nowrap rounded-full border border-[#C9CFC9] bg-white px-3.5 text-[14px] font-medium tabular-nums text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:border-white/[0.18] dark:bg-[#1f2225] dark:text-white">
      {batch.busy ? <span className={`${styles.spinner} rounded-full`} aria-hidden="true" /> : null}
      {uploadSummaryText(t, batch, batch.busy ? queue.progress : null, "chip")}
    </button>
  );
}
