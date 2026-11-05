"use client";

import type { ReactNode } from "react";
import { useTransaccionesWords } from "./transacciones-words";
import styles from "./records-filter-preview.module.css";

type Option<T extends string> = { value: T; label: string; icon?: ReactNode; description?: string };

export default function RecordsFilterSelection<T extends string>({ options, selected, onChange, query = "", keepSelectedVisible = false }: { options: readonly Option<T>[]; selected: T[]; onChange: (selected: T[]) => void; query?: string; keepSelectedVisible?: boolean }) {
  const { t } = useTransaccionesWords();
  const word = (key: string) => t(`business.transactions.layout.filters.${key}`);
  const search = query.trim().toLocaleLowerCase();
  const visible = options.filter(option => `${option.label}${option.description ? ` ${option.description}` : ""}`.toLocaleLowerCase().includes(search));
  const visibleValues = visible.map(option => option.value);
  const selectedCount = visibleValues.filter(value => selected.includes(value)).length;
  const all = visible.length > 0 && selectedCount === visible.length;
  const mixed = selectedCount > 0 && !all;
  const pinned = keepSelectedVisible ? options.filter(option => selected.includes(option.value) && !visibleValues.includes(option.value)) : [];
  const chooseVisible = () => onChange(all ? selected.filter(value => !visibleValues.includes(value)) : [...new Set([...selected, ...visibleValues])]);
  return <>
    <label className={`${styles.choice} ${styles.parentChoice}`}>
      <input type="checkbox" checked={all} disabled={visible.length === 0} aria-checked={mixed ? "mixed" : all} ref={node => { if (node) node.indeterminate = mixed; }} onChange={chooseVisible} />
      <span>{word(search ? "select_results" : "select_all")}</span>
    </label>
    {search ? <p className={styles.hint}>{word("visible_selection_hint")}</p> : null}
    <div className={styles.options}>{[...pinned, ...visible].map(option => <label key={option.value} className={styles.choice}>
      <input type="checkbox" checked={selected.includes(option.value)} onChange={() => onChange(selected.includes(option.value) ? selected.filter(value => value !== option.value) : [...selected, option.value])} />
      {option.icon}
      <span className={option.description ? "min-w-0 break-all" : undefined}>{option.description ? <><span className="block">{option.label}</span><small className="block text-[12px] opacity-70">{option.description}</small></> : option.label}</span>
    </label>)}</div>
    {visible.length === 0 ? <p className={styles.hint}>{word("no_matches")}</p> : null}
  </>;
}
