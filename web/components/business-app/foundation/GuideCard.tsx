"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import { X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { dismissBusinessGuideCard, getBusinessGuideCard, type BusinessGuideCardId } from "@/lib/business-guide-api";
import { serverRequestReference } from "@/lib/failure-screen";
import styles from "./guide-card.module.css";

type GuidePoint = { label: string; body: string };
type Props = {
  cardId: BusinessGuideCardId;
  userId: string;
  title: string;
  points: [GuidePoint, GuidePoint, GuidePoint];
  /** Called once the read settles: whether the card takes space. A failed read shows its retry, so it counts as shown. */
  onKnown?: (shown: boolean) => void;
  /** Held, the card still reads but draws nothing, so a screen can draw it in the same frame as the rest. */
  held?: boolean;
};

type State =
  | { kind: "loading" | "hidden" | "visible" | "saving" }
  | { kind: "read-failed" | "save-failed"; reference: string | null };

export default function GuideCard(props: Props) {
  return <GuideCardForPerson key={JSON.stringify([props.userId, props.cardId])} {...props} />;
}

function GuideCardForPerson({ cardId, userId, title, points, onKnown, held = false }: Props) {
  const { t } = useTranslation();
  const titleId = useId();
  const request = useRef<AbortController | null>(null);
  const [state, setState] = useState<State>({ kind: "loading" });
  const perform = useCallback(async (action: "read" | "dismiss") => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    const options = { cardId, expectedUserId: userId, signal: controller.signal };
    try {
      const { dismissed } = await (action === "read" ? getBusinessGuideCard(options) : dismissBusinessGuideCard(options));
      if (!controller.signal.aborted) setState({ kind: dismissed ? "hidden" : "visible" });
    } catch (error) {
      if (!controller.signal.aborted) setState({
        kind: action === "read" ? "read-failed" : "save-failed",
        reference: serverRequestReference(error),
      });
    }
  }, [cardId, userId]);

  useEffect(() => {
    void perform("read");
    return () => request.current?.abort();
  }, [perform]);

  useEffect(() => {
    if (state.kind !== "loading") onKnown?.(state.kind !== "hidden");
  }, [state.kind, onKnown]);

  if (held || state.kind === "loading" || state.kind === "hidden") return null;

  const read = () => {
    setState({ kind: "loading" });
    void perform("read");
  };
  const dismiss = () => {
    setState({ kind: "saving" });
    void perform("dismiss");
  };
  const failure = state.kind === "read-failed" || state.kind === "save-failed" ? (
    <div className={styles.failure} role="alert">
      <p>
        {t(state.kind === "read-failed" ? "business.guide_cards.placeholder.read_failed" : "business.guide_cards.placeholder.save_failed")}
        {state.reference ? <span className={styles.reference}><ReferenceCode reference={state.reference} /></span> : null}
      </p>
      <button type="button" className={styles.retry} onClick={state.kind === "read-failed" ? read : dismiss}>{t("common.retry")}</button>
    </div>
  ) : null;

  if (state.kind === "read-failed") return failure;

  const saving = state.kind === "saving";
  return (
    <section className={`${styles.card} rounded-surface`} aria-labelledby={titleId} aria-busy={saving}>
      <header className={styles.header}>
        <h3 className="font-display" id={titleId}>{title}</h3>
        <button type="button" className={`${styles.close} rounded-full`} aria-label={t("business.guide_cards.placeholder.dismiss")} onClick={dismiss} disabled={saving}>
          <X size={18} aria-hidden="true" />
        </button>
      </header>
      <ul className={styles.points}>
        {points.map(({ label, body }) => (
          <li key={label}>
            <strong>{label}</strong>
            <p>{body}</p>
          </li>
        ))}
      </ul>
      {failure}
    </section>
  );
}

