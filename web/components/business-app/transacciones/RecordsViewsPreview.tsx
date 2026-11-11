"use client";

import { useCallback, useEffect, useId, useRef, useState, type ReactNode } from "react";
import { Bookmark, Check, Pencil, Plus, RotateCcw, Trash2, X } from "lucide-react";
import type { RecordsViewPreferences } from "./records-view-preferences";
import type { Period } from "../business-format";
import type { RecordsFilter } from "./RecordsToolbar";
import type { PreviewFilters } from "./records-filter-preview-model";
import RecordsPreviewPopover from "./RecordsPreviewPopover";
import { useTransaccionesWords } from "./transacciones-words";
import { dismissToast, showToast } from "../foundation/toasts";
import pointerAffordances from "@/components/sidebar/pointerAffordances.module.css";

export type RecordsViewSelection = { record: RecordsFilter; period: Period; filters: PreviewFilters; preferences?: RecordsViewPreferences };
export type SavedRecordsView = { id: string; name: string; selection: RecordsViewSelection };

/** Restores the deleted view. Resolves false when the restore did not land, so Deshacer stays offered. If Reintentar later lands an unconfirmed restore, `landed` runs. */
export type UndoDelete = (landed: () => void) => Promise<boolean>;
export type RecordsViews = {
  items: { id: string; name: string }[];
  applied: { id: string; changed: boolean } | null;
  select: (id: string) => void;
  save: (name: string) => Promise<boolean>;
  rename: (id: string, name: string) => Promise<boolean>;
  saveChanges: (id: string) => Promise<boolean>;
  remove: (id: string) => Promise<UndoDelete | null>;
  busy: boolean;
  notice: ReactNode;
};

const keySortedJson = (value: unknown) => JSON.stringify(value, (_key, inner: unknown) => inner && typeof inner === "object" && !Array.isArray(inner)
  ? Object.fromEntries(Object.entries(inner).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0)))
  : inner);
export const sameRecipe = (a: unknown, b: unknown) => keySortedJson(a) === keySortedJson(b);

const MAX_NAME = 120;
const FOOTER = "footer";
type Editing = { kind: "rename"; id: string; name: string } | { kind: "create"; name: string } | null;

const rowClass = "group relative flex min-h-11 items-center gap-2.5 rounded-item pl-2.5 pr-1.5 text-[15px] text-[#172b26] transition-colors duration-150 ease-out motion-reduce:transition-none hover:bg-[#F1F2EE] focus-within:bg-[#F1F2EE] has-[>button:focus-visible]:outline has-[>button:focus-visible]:outline-2 has-[>button:focus-visible]:-outline-offset-2 has-[>button:focus-visible]:outline-[var(--cuadrao-green)] dark:text-white dark:hover:bg-white/5 dark:focus-within:bg-white/5";
const iconButtonClass = "group/icon relative inline-flex size-8 shrink-0 items-center justify-center rounded-item text-[#56635e] hover:bg-[#E4E7E1] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40 dark:text-white/65 dark:hover:bg-white/10 dark:hover:text-white";
const footerActionClass = "flex min-h-11 w-full items-center gap-2.5 rounded-item px-2.5 text-left text-[15px] font-medium text-[var(--cuadrao-green)] hover:bg-[#F1F2EE] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-45 dark:hover:bg-white/5";
const fieldClass = "h-9 min-w-0 flex-1 rounded-item border border-[var(--cuadrao-green)] bg-white px-2.5 text-[16px] text-[#172b26] outline-none ring-[3px] ring-[var(--cuadrao-green)]/15 placeholder:text-[#7d8a84] dark:bg-[#1f2225] dark:text-white dark:placeholder:text-white/45";

export function RecordsViewsPreview({ views }: { views: RecordsViews }) {
  const { t } = useTransaccionesWords();
  const cancelEdit = useRef<(() => boolean) | null>(null);
  const registerCancel = useCallback((cancel: (() => boolean) | null) => { cancelEdit.current = cancel; }, []);
  const applied = views.items.find((view) => view.id === views.applied?.id);
  return <RecordsPreviewPopover label={t("business.transactions.layout.views.title")} currentLabel={applied?.name} beforeEscape={() => cancelEdit.current?.() ?? false} icon={<Bookmark size={17} aria-hidden="true" fill={applied ? "currentColor" : "none"} className={applied ? "text-[var(--cuadrao-green)]" : undefined} />} width={320}>
    {(close) => <ViewsMenu views={views} close={close} registerCancel={registerCancel} />}
  </RecordsPreviewPopover>;
}

function ViewsMenu({ views, close, registerCancel }: { views: RecordsViews; close: () => void; registerCancel: (cancel: (() => boolean) | null) => void }) {
  const { t } = useTransaccionesWords();
  const word = (key: string, values?: Record<string, string>) => t(`business.transactions.layout.views.${key}`, values);
  const [editing, setEditing] = useState<Editing>(null);
  const menuId = useId();
  const names = useRef(new Map<string, HTMLButtonElement>());
  const footer = useRef<HTMLButtonElement>(null);
  const pendingFocus = useRef<string | null>(null);
  const applied = views.items.find((view) => view.id === views.applied?.id);
  const changed = Boolean(applied && views.applied?.changed);
  const taken = (name: string, except?: string) => views.items.some((view) => view.id !== except && view.name.toLocaleLowerCase() === name.trim().toLocaleLowerCase());
  const finish = (focus: string) => { pendingFocus.current = focus; setEditing(null); };
  useEffect(() => {
    registerCancel(editing ? () => { pendingFocus.current = editing.kind === "rename" ? editing.id : FOOTER; setEditing(null); return true; } : null);
    return () => registerCancel(null);
  }, [editing, registerCancel]);
  useEffect(() => {
    const target = pendingFocus.current;
    if (!target) return;
    const node = target === FOOTER ? footer.current : names.current.get(target);
    if (!node) return;
    pendingFocus.current = null;
    node.focus();
  });
  const remove = async (id: string, name: string) => {
    const index = views.items.findIndex((view) => view.id === id);
    pendingFocus.current = views.items[index + 1]?.id ?? views.items[index - 1]?.id ?? FOOTER;
    const undo = await views.remove(id);
    if (!undo) return;
    let offered = 0;
    const offerUndo = () => { offered = showToast({ kind: "success", text: word("deleted", { name }), action: { label: t("business.transactions.undo"), run: () => { void undo(() => dismissToast(offered)).then((restored) => { if (!restored) offerUndo(); }); } } }); };
    offerUndo();
  };
  const nameRef = (id: string) => (node: HTMLButtonElement | null) => { if (node) names.current.set(id, node); else names.current.delete(id); };

  return <>
    <div className="px-3.5 pb-2 pt-3"><h3 className="text-[13px] font-medium uppercase tracking-[.06em] text-[#56635e] dark:text-white/60">{word("title")}</h3></div>
    {views.notice ? <div className="px-3.5">{views.notice}</div> : null}
    {views.items.length ? <ul className="flex flex-col gap-0.5 px-1.5 pb-1.5">
      {views.items.map((view) => editing?.kind === "rename" && editing.id === view.id ? <li key={view.id}>
        <NameForm value={editing.name} label={word("name")} duplicateText={word("duplicate")} onChange={(name) => setEditing({ ...editing, name })} duplicate={taken(editing.name, view.id)} busy={views.busy} className="rounded-item bg-[#F1F2EE] py-1 pl-2.5 pr-1.5 dark:bg-white/5"
          onSubmit={(name) => { if (name === view.name) { finish(view.id); return; } void views.rename(view.id, name).then((saved) => { if (saved) finish(view.id); }); }}
          actions={<>
            <button type="submit" aria-label={word("rename_save")} disabled={!editing.name.trim() || taken(editing.name, view.id) || views.busy} className={`${iconButtonClass} text-[var(--cuadrao-green)]`}><Check size={18} strokeWidth={2.4} aria-hidden="true" /></button>
            <button type="button" aria-label={t("common.cancel")} onClick={() => finish(view.id)} className={iconButtonClass}><X size={16} aria-hidden="true" /></button>
          </>} />
      </li> : <li key={view.id} className={rowClass}>
        <span className="flex w-4 shrink-0 text-[var(--cuadrao-green)]">{view.id === applied?.id ? <Check size={16} strokeWidth={2.6} aria-hidden="true" /> : null}</span>
        <button type="button" ref={nameRef(view.id)} aria-current={view.id === applied?.id ? "true" : undefined} aria-describedby={view.id === applied?.id && changed ? `${menuId}-changed` : undefined} onClick={() => { views.select(view.id); close(); }} className={`h-11 min-w-0 flex-1 truncate text-left focus-visible:outline-none ${view.id === applied?.id ? "font-semibold" : ""}`}>{view.name}</button>
        {view.id === applied?.id && changed ? <span id={`${menuId}-changed`} className="flex shrink-0 items-center gap-1 whitespace-nowrap text-[12.5px] text-[#7a5512] dark:text-[#e3b65c]"><span aria-hidden="true" className="size-1.5 rounded-full bg-[#b07d1a]" />{word("changed")}</span> : null}
        <span className={`flex shrink-0 transition-opacity duration-150 ease-out motion-reduce:transition-none ${pointerAffordances.rowActions}`}>
          <IconButton label={word("rename_named", { name: view.name })} tip={t("common.rename")} disabled={views.busy || Boolean(editing)} onClick={() => setEditing({ kind: "rename", id: view.id, name: view.name })}><Pencil size={16} aria-hidden="true" /></IconButton>
          <IconButton label={word("delete_named", { name: view.name })} tip={t("common.delete")} disabled={views.busy || Boolean(editing)} onClick={() => void remove(view.id, view.name)}><Trash2 size={16} aria-hidden="true" /></IconButton>
        </span>
      </li>)}
    </ul> : <p className="px-3.5 pb-3.5 pt-1.5 text-[14px] leading-[1.45] text-[#56635e] dark:text-white/60">{word("empty")} {word("empty_hint")}</p>}
    <div className="border-t border-[#EEF0EC] p-1.5 dark:border-white/10">
      {editing?.kind === "create" ? <NameForm value={editing.name} label={word("name")} placeholder={word("placeholder")} hint={word("save_hint")} duplicateText={word("duplicate")} onChange={(name) => setEditing({ kind: "create", name })} duplicate={taken(editing.name)} busy={views.busy} className="p-1"
          onSubmit={(name) => { void views.save(name).then((saved) => { if (saved) close(); }); }}
          actions={<button type="submit" disabled={!editing.name.trim() || taken(editing.name) || views.busy} className="inline-flex h-9 shrink-0 items-center rounded-full bg-[var(--cuadrao-green)] px-3.5 text-[14px] font-medium text-[var(--cuadrao-cream)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] disabled:opacity-40">{t("common.save")}</button>} /> : changed && applied ? <div className="flex flex-col gap-0.5">
        <button type="button" ref={footer} disabled={views.busy || Boolean(editing)} className={footerActionClass} onClick={() => { void views.saveChanges(applied.id).then((saved) => { if (saved) close(); }); }}><RotateCcw size={16} aria-hidden="true" />{word("save_changes", { name: applied.name })}</button>
        <button type="button" disabled={views.busy || Boolean(editing)} className={footerActionClass} onClick={() => setEditing({ kind: "create", name: "" })}><Plus size={16} aria-hidden="true" />{word("save_new")}</button>
      </div> : <button type="button" ref={footer} disabled={views.busy || Boolean(editing)} className={footerActionClass} onClick={() => setEditing({ kind: "create", name: "" })}><Plus size={16} aria-hidden="true" />{word("save")}</button>}
    </div>
  </>;
}

function IconButton({ label, tip, disabled, onClick, children }: { label: string; tip: string; disabled: boolean; onClick: () => void; children: ReactNode }) {
  return <button type="button" aria-label={label} disabled={disabled} onClick={onClick} className={iconButtonClass}>
    {children}
    <span aria-hidden="true" className="pointer-events-none absolute bottom-full right-0 mb-1 whitespace-nowrap rounded-mark bg-[#172b26] px-2 py-1 text-[12px] text-[#F7F5EE] opacity-0 transition-opacity duration-150 ease-out motion-reduce:transition-none group-hover/icon:opacity-100 group-focus-visible/icon:opacity-100 dark:bg-white dark:text-[#172b26]">{tip}</span>
  </button>;
}

function NameForm({ value, label, placeholder, hint, duplicate, duplicateText, busy, className, onChange, onSubmit, actions }: { value: string; label: string; placeholder?: string; hint?: string; duplicate: boolean; duplicateText: string; busy: boolean; className: string; onChange: (value: string) => void; onSubmit: (name: string) => void; actions: ReactNode }) {
  const lineId = useId();
  const line = duplicate ? duplicateText : hint;
  return <>
    <form className={`flex items-center gap-1.5 ${className}`} onSubmit={(event) => { event.preventDefault(); if (value.trim() && !duplicate && !busy) onSubmit(value.trim()); }}>
      <input autoFocus aria-label={label} aria-invalid={duplicate || undefined} aria-describedby={line ? lineId : undefined} value={value} onChange={(event) => onChange(event.target.value)} maxLength={MAX_NAME} placeholder={placeholder} required className={fieldClass} />
      {actions}
    </form>
    {duplicate ? <p id={lineId} role="alert" className="mx-2.5 mb-0.5 mt-1.5 text-[13px] text-[#9e2f39] dark:text-[#ec9aa0]">{line}</p>
      : line ? <p id={lineId} className="mx-2.5 mt-1 text-[12.5px] text-[#56635e] dark:text-white/60">{line}</p> : null}
  </>;
}
