"use client";

import { useEffect, useRef } from "react";
import { useTranslation } from "react-i18next";
import { EmptyState } from "./foundation/EmptyState";

/** The end of a run through the Bandeja: nothing is left to review, and one way back. */
export default function ReceiptReviewDone({ onBack }: { onBack: () => void }) {
  const { t } = useTranslation();
  const box = useRef<HTMLDivElement>(null);
  // The button that brought the person here is gone, so focus lands on what replaced it.
  useEffect(() => { box.current?.focus(); }, []);
  return (
    <div ref={box} tabIndex={-1} role="status" className="outline-none">
      <EmptyState
        kind="done"
        testId="receipt-review-done"
        title={t("business.dossier.placeholder.done_title", "No receipts left to review")}
        action={{ label: t("business.dossier.placeholder.done_back", "Back to Inbox"), run: onBack }}
      />
    </div>
  );
}
