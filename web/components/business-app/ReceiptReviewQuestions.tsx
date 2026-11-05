"use client";

import { useTranslation } from "react-i18next";
import type { BusinessReviewQuestion } from "@/lib/business-dossier";
import { SURFACE_CARD } from "./foundation/surfaces";

export default function ReceiptReviewQuestions({ questions }: { questions: BusinessReviewQuestion[] }) {
  const { t } = useTranslation();
  const unresolved = questions.filter((question) => ["open", "owner_does_not_know", "waiting_for_window"].includes(question.state));
  if (!unresolved.length) return null;
  return (
    <section className={SURFACE_CARD} aria-labelledby="receipt-questions-title" data-testid="receipt-review-questions">
      <h3 id="receipt-questions-title" className="text-[14px] font-medium text-black dark:text-white">{t("business.dossier.decisions", "Needs your decision")}</h3>
      <ul className="mt-3 space-y-3">
        {unresolved.map((question) => (
          <li key={question.id} className="text-[14px] leading-relaxed text-black/80 dark:text-white/80">
            <p>{question.prompt}</p>
            <p className="mt-1 text-[12px] text-black/55 dark:text-white/55">{t(`business.dossier.question.${question.state}`, question.state)} · {question.asked_of === "accountant" ? t("business.dossier.for_accountant", "For the accountant") : t("business.dossier.for_owner", "For the owner")}</p>
          </li>
        ))}
      </ul>
    </section>
  );
}
