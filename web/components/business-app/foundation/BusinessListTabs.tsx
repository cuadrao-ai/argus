"use client";

import { useRef, type ReactNode } from "react";
import styles from "./BusinessListTabs.module.css";

export default function BusinessListTabs<T extends string>({ items, value, onChange, label, idPrefix, controls }: {
  items: readonly { value: T; label: ReactNode }[];
  value: T;
  onChange: (value: T) => void;
  label: string;
  idPrefix: string;
  controls?: string;
}) {
  const tabs = useRef<HTMLDivElement>(null);
  return <div ref={tabs} className={styles.tabs} role="tablist" aria-label={label} onKeyDown={event => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    event.preventDefault();
    const index = items.findIndex(item => item.value === value);
    const next = event.key === "Home" ? 0 : event.key === "End" ? items.length - 1 : (index + (event.key === "ArrowRight" ? 1 : -1) + items.length) % items.length;
    onChange(items[next].value);
    tabs.current?.querySelectorAll<HTMLButtonElement>("button")[next]?.focus();
  }}>
    {items.map(item => <button key={item.value} id={`${idPrefix}-${item.value}`} type="button" role="tab" aria-selected={value === item.value} aria-controls={controls} tabIndex={value === item.value ? 0 : -1} onClick={() => onChange(item.value)}>{item.label}</button>)}
  </div>;
}
