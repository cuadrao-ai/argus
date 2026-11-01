"use client";

import { useCallback, useRef, type CSSProperties } from "react";
import { cardsVars } from "@/lib/landing-timeline";
import { scrollProgress } from "@/lib/scene-timeline";
import { landingCopy, type LandingLocale } from "./landing-copy";
import styles from "./problem-cards.module.css";
import { useScrollFrame, type ScrollFrame } from "./use-scroll-frame";

// Where each document starts before the cards line up: x, y, rotation.
const SCATTER = [
  [-330, 24, -7],
  [340, -16, 6],
  [-250, 70, 5],
  [300, 50, -5],
  [-60, 150, -4],
];

const TONE = {
  done: styles.chipDone,
  wait: styles.chipWait,
  plain: "",
  alert: styles.chipAlert,
} as const;

export function ProblemCards({ locale }: { locale: LandingLocale }) {
  const copy = landingCopy[locale].problem;
  const section = useRef<HTMLElement>(null);
  const field = useRef<HTMLDivElement>(null);

  const paint = useCallback(({ width, height, reduced }: ScrollFrame) => {
    const box = section.current?.getBoundingClientRect();
    if (!box || !field.current) return;
    const progress = reduced ? 1 : scrollProgress(box.top, box.height, height);
    for (const [name, value] of Object.entries(cardsVars(progress, width, height))) {
      field.current.style.setProperty(name, value);
    }
  }, []);
  useScrollFrame(paint);

  return (
    <section ref={section} className={styles.cards} id="problema" aria-labelledby="problem-title">
      <div className={styles.pin}>
        <div ref={field} className={styles.field} data-cards-field>
          <div className={styles.titles}>
            <div className={styles.before}>
              <h2 id="problem-title">{copy.before.title}</h2>
              <p>{copy.before.body}</p>
            </div>
            <div className={styles.after}>
              <h2>{copy.after.title}</h2>
              <p>{copy.after.body}</p>
            </div>
          </div>
          <div className={styles.list}>
            {copy.documents.map((document, index) => {
              const [dx, dy, turn] = SCATTER[index];
              const scatter = { "--dx": `${dx}px`, "--dy": `${dy}px`, "--turn": `${turn}deg` } as CSSProperties;
              return (
                <div key={document.name} className={styles.document} style={scatter}>
                  <div>
                    <b>{document.name}</b>
                    <span>{document.detail}</span>
                  </div>
                  <span className={`${styles.chip} ${TONE[document.tone]}`}>{document.state}</span>
                </div>
              );
            })}
          </div>
        </div>
      </div>
    </section>
  );
}
