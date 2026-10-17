"use client";

import { useRef, type KeyboardEvent } from "react";
import styles from "./owner-stories.module.css";

export function OwnerStoryControls<T extends string>({ id, label, steps, selected, onSelect }: {
  id: string;
  label: string;
  steps: readonly { id: T; title: string; body: string }[];
  selected: T;
  onSelect: (id: T) => void;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  function onKey(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const next = event.key === "ArrowDown" || event.key === "ArrowRight" ? (index + 1) % steps.length
      : event.key === "ArrowUp" || event.key === "ArrowLeft" ? (index + steps.length - 1) % steps.length
      : event.key === "Home" ? 0 : event.key === "End" ? steps.length - 1 : null;
    if (next === null) return;
    event.preventDefault();
    onSelect(steps[next].id);
    refs.current[next]?.focus();
  }
  return <div className={styles.stepList} role="tablist" aria-orientation="vertical" aria-label={label}>
    {steps.map((step, index) => <button type="button" role="tab" key={step.id} id={`${id}-tab-${step.id}`} aria-controls={`${id}-panel`} aria-selected={selected === step.id} tabIndex={selected === step.id ? 0 : -1} onClick={() => onSelect(step.id)} onKeyDown={(event) => onKey(event, index)} ref={(node) => { refs.current[index] = node; }}>
      <span className={styles.stepNumber}>{String(index + 1).padStart(2, "0")}</span><span><strong>{step.title}</strong><small>{step.body}</small></span>
    </button>)}
  </div>;
}
