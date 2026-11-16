"use client";

import { useId, useState, type CSSProperties } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { usePanelShell } from "@/components/chat/ChatWorkspace";
import type { BusinessGuideCardId } from "@/lib/business-guide-api";
import { serverRequestReference } from "@/lib/failure-screen";
import styles from "./guide-card.module.css";

type GuidePoint = { label: string; body: string };
type Props = {
  cardId: BusinessGuideCardId;
  title: string;
  points: [GuidePoint, GuidePoint, GuidePoint];
  /** While its screen is pending, the card holds its own size and place with nothing in it. */
  pending?: boolean;
};

const empty: CSSProperties = { visibility: "hidden" };

/** Shown until the person dismisses it. Whether they did comes with the shell's account; unknown shows nothing. */
export default function GuideCard(props: Props) {
  const shell = usePanelShell();
  return <GuideCardForPerson key={shell?.memberId ?? ""} {...props} />;
}

function GuideCardForPerson({ cardId, title, points, pending = false }: Props) {
  const { t } = useTranslation();
  const titleId = useId();
  const shell = usePanelShell();
  const [saveFailure, setSaveFailure] = useState<{ reference: string | null } | null>(null);
  const dismissed = shell?.dismissedGuideCards;
  if (!dismissed || dismissed.includes(cardId)) return null;

  const dismiss = () => {
    setSaveFailure(null);
    void shell?.dismissGuideCard?.(cardId).catch((error: unknown) => setSaveFailure({ reference: serverRequestReference(error) }));
  };
  const hidden = pending ? empty : undefined;
  return (
    <section className={`${styles.card} rounded-surface`} aria-labelledby={pending ? undefined : titleId} aria-hidden={pending || undefined} data-guide-slot={pending ? "" : undefined}>
      <header className={styles.header} style={hidden}>
        <h3 className="font-display" id={pending ? undefined : titleId}>{title}</h3>
        <button type="button" className={`${styles.close} rounded-full`} aria-label={t("business.guide_cards.placeholder.dismiss")} onClick={dismiss}>
          <X size={18} aria-hidden="true" />
        </button>
      </header>
      <ul className={styles.points} style={hidden}>
        {points.map(({ label, body }) => (
          <li key={label}>
            <strong>{label}</strong>
            <p>{body}</p>
          </li>
        ))}
      </ul>
      {saveFailure && !pending ? (
        <div className={styles.failure} role="alert">
          <p>
            {t("business.guide_cards.placeholder.save_failed")}
            {saveFailure.reference ? <span className={styles.reference}><ReferenceCode reference={saveFailure.reference} /></span> : null}
          </p>
          <button type="button" className={styles.retry} onClick={dismiss}>{t("common.retry")}</button>
        </div>
      ) : null}
    </section>
  );
}
