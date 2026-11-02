"use client";

import { useEffect, useId, useRef, useState } from "react";
import styles from "./faq-list.module.css";

const OPEN_MS = 220;

type Item = { question: string; answer: string };

export function FaqList({ items }: { items: readonly Item[] }) {
  const id = useId();
  const list = useRef<HTMLDivElement>(null);
  const clicked = useRef(false);
  const [open, setOpen] = useState<number | null>(0);

  // Closing a long answer above can move the new question under the header.
  useEffect(() => {
    if (!clicked.current || open === null) return;
    const timer = window.setTimeout(() => {
      list.current
        ?.querySelector('[aria-expanded="true"]')
        ?.scrollIntoView({ block: "nearest" });
    }, OPEN_MS);
    return () => window.clearTimeout(timer);
  }, [open]);

  return (
    <div ref={list} className={styles.list}>
      {items.map((item, index) => {
        const expanded = open === index;
        return (
          <div key={item.question} className={`${styles.item} ${expanded ? styles.on : ""}`}>
            <h3 className={styles.heading}>
              <button
                type="button"
                id={`${id}-q${index}`}
                className={styles.question}
                aria-expanded={expanded}
                aria-controls={`${id}-a${index}`}
                onClick={() => {
                  clicked.current = true;
                  setOpen(expanded ? null : index);
                }}
              >
                {item.question}
                <span className={styles.mark} aria-hidden="true" />
              </button>
            </h3>
            <div
              id={`${id}-a${index}`}
              className={styles.answer}
              role="region"
              aria-labelledby={`${id}-q${index}`}
            >
              <div className={styles.clip}>
                <p>{item.answer}</p>
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
