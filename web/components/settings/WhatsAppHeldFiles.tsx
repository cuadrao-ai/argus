"use client";

import { Briefcase, Check, ChevronDown, Inbox, LoaderCircle } from "lucide-react";
import { useCallback, useContext, useEffect, useEffectEvent, useId, useLayoutEffect, useRef, useState, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { createPortal } from "react-dom";
import type { TFunction } from "i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import BottomSheet from "@/components/ui/BottomSheet";
import { BusinessContext } from "@/components/business-app/business-context";
import { primaryButtonClass, secondaryButtonClass } from "@/components/business-app/business-ui";
import { dismissToast, showToast } from "@/components/business-app/foundation/toasts";
import { FOCUS_RING } from "@/components/business-app/foundation/presentation";
import { ToastViewport } from "@/components/business-app/foundation/ToastViewport";
import { todayIso } from "@/components/business-app/business-format";
import { dueDistance } from "@/lib/business-month-close";
import { getWhatsAppHeldFiles, assignWhatsAppHeldFile, type WhatsAppHeldFile, type WhatsAppHeldFilesResponse, type WhatsAppLinkError } from "@/lib/whatsapp-link-api";
import { WhatsAppHeldFilePreview } from "./WhatsAppHeldFilePreview";

type Business = WhatsAppHeldFilesResponse["receiving_businesses"][number];
const muted = "text-sm leading-5 text-[#56635e] dark:text-white/70";
const reasonKey: Record<WhatsAppHeldFile["reason"], string> = {
  no_buyer_rnc: "settings.whatsapp.held.reason.no_buyer_rnc",
  no_match: "settings.whatsapp.held.reason.no_match",
  two_matches: "settings.whatsapp.held.reason.two_matches",
  no_eligible_business: "business.dossier.placeholder.gap.not_read.title",
  read_failed: "business.bandeja.label.cant_read",
  held_read_cap: "business.file_read.held_day",
};

function receivedAt(stamp: string, locale: string) {
  const date = new Date(stamp);
  const distance = dueDistance(todayIso(date), todayIso());
  const day = distance && distance.days <= 1 && distance.direction !== "future"
    ? new Intl.RelativeTimeFormat(locale, { numeric: "auto" }).format(-distance.days, "day")
    : date.toLocaleDateString(locale, { day: "numeric", month: "short" });
  return day + ", " + date.toLocaleTimeString(locale, { hour: "numeric", minute: "2-digit" });
}

function expiry(stamp: string, t: TFunction) {
  const distance = dueDistance(todayIso(new Date(stamp)), todayIso());
  if (!distance || distance.direction !== "future") return t("business.dossier.supporting.purge_today");
  if (distance.days === 1) return t("business.dossier.supporting.purge_tomorrow");
  return t("business.dossier.supporting.purge_in", { count: distance.days });
}

function BusinessIcon() {
  return <span aria-hidden="true" className="grid size-8 shrink-0 place-items-center rounded-item bg-[#E8E6DE] text-[#3d4a45] dark:bg-white/[.08] dark:text-white/80"><Briefcase size={16} /></span>;
}

function BusinessPicker({ businesses, selected, disabled, onChoose }: {
  businesses: Business[]; selected?: Business; disabled: boolean; onChoose: (business: Business) => void;
}) {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const id = useId();
  const root = useRef<HTMLDivElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const initial = useRef<HTMLButtonElement>(null);
  const [open, setOpen] = useState(false);
  const [menu, setMenu] = useState({ above: false, maxHeight: 300 });
  const label = t("business.switcher.choose");
  const toggle = () => {
    const rect = trigger.current?.getBoundingClientRect();
    const viewport = root.current?.closest(".argus-thin-scrollbar")?.getBoundingClientRect();
    if (rect) {
      const below = (viewport?.bottom || window.innerHeight) - rect.bottom - 6;
      const above = rect.top - (viewport?.top ?? 0) - 6;
      const openAbove = below < 14 + businesses.length * 44 && above > below;
      setMenu({ above: openAbove, maxHeight: Math.max(44, openAbove ? above : below) });
    }
    setOpen(!open);
  };
  const close = () => { setOpen(false); trigger.current?.focus(); };
  const active = businesses.some(b => b.space_id === selected?.space_id) ? selected : businesses[0];
  useOverlayLayer({ isOpen: open && !isBelowTablet, overlayId: id, containerRef: root,
    onEscape: close, onOutsidePointerDown: () => setOpen(false) });
  useLayoutEffect(() => { if (open && !isBelowTablet) initial.current?.focus(); }, [open, isBelowTablet]);
  function navigate(event: KeyboardEvent<HTMLUListElement>) {
    const options = Array.from(event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="option"]'));
    const index = options.indexOf(document.activeElement as HTMLButtonElement);
    let next = index;
    if (event.key === "ArrowDown") next = (index + 1) % options.length;
    else if (event.key === "ArrowUp") next = (index - 1 + options.length) % options.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = options.length - 1;
    else return;
    event.preventDefault();
    options[next]?.focus();
  }
  const list = <ul id={id} role="listbox" aria-label={label} onKeyDown={navigate} style={isBelowTablet ? undefined : { maxHeight: menu.maxHeight }} className={isBelowTablet ? "-mx-2" :
    `absolute left-0 z-10 w-[min(300px,100%)] overflow-y-auto rounded-surface border border-[var(--surface-divider)] bg-white p-1.5 dark:bg-[#1f2225] ${menu.above ? "bottom-full mb-1.5" : "top-full mt-1.5"}`}>
    {businesses.map(b => <li role="none" key={b.space_id}>
      <button ref={b.space_id === active?.space_id ? initial : undefined} type="button" role="option" aria-selected={b.space_id === selected?.space_id}
        className={`flex w-full items-center gap-3 rounded-item text-left hover:bg-black/[.06] aria-selected:bg-black/[.06] dark:hover:bg-white/[.08] dark:aria-selected:bg-white/[.08] ${isBelowTablet ? "h-14 px-3" : "min-h-11 px-2.5"}`}
        onClick={() => { setOpen(false); onChoose(b); }}>
        {isBelowTablet && <BusinessIcon />}<span className="min-w-0 flex-1 truncate">{b.name}</span>
        {selected?.space_id === b.space_id && <Check size={18} aria-hidden="true" className="text-[var(--cuadrao-green)]" />}
      </button>
    </li>)}
  </ul>;
  return <div ref={root} className="relative min-w-0 flex-1" onBlur={event => {
    if (open && !isBelowTablet && event.relatedTarget && !event.currentTarget.contains(event.relatedTarget)) setOpen(false);
  }}>
    <button ref={trigger} data-held-control="" type="button" aria-label={label} aria-expanded={open} aria-haspopup="listbox" aria-controls={open ? id : undefined}
      className={`flex min-h-11 w-full items-center gap-2 rounded-item border border-[#7d8a84] bg-white px-3 text-left disabled:opacity-50 dark:border-white/25 dark:bg-transparent ${FOCUS_RING}`}
      disabled={disabled} onClick={toggle} onKeyDown={event => { if (event.key === "ArrowDown" && !open) { event.preventDefault(); toggle(); } }}>
      <span className={`min-w-0 flex-1 truncate ${selected ? "" : "text-[#56635e] dark:text-white/70"}`}>{selected?.name ?? label}</span>
      <ChevronDown size={18} aria-hidden="true" className="shrink-0"/>
    </button>
    {open && (isBelowTablet
      ? <BottomSheet isOpen snaps="fit" title={label} closeLabel={t("common.close")} onClose={close} initialFocusRef={initial}>{list}</BottomSheet>
      : list)}
  </div>;
}

function FileRow({ file, businesses, busy, problem, onAssign }: {
  file: WhatsAppHeldFile; businesses: Business[]; busy: string | null; problem?: string;
  onAssign: (file: WhatsAppHeldFile, target: Business) => void;
}) {
  const { t, i18n } = useTranslation();
  const [chosen, setChosen] = useState<Business>();
  const assign = useRef<HTMLButtonElement>(null);
  const fixed = businesses.length === 1 && (!chosen || chosen.space_id === businesses[0].space_id);
  const target = fixed ? businesses[0] : businesses.find(b => b.space_id === chosen?.space_id);
  const reading = file.reading;
  const busyHere = busy === file.id;
  const denied = problem === "business_permission_denied" && !target;
  const error = denied ? "workspace_setup_preview.upload_denied" : problem === "failed" ? "settings.whatsapp.problem_failed" : undefined;
  const title = t(reading ? "business.bandeja.label.reading" : reasonKey[file.reason]);
  return <li data-held-file={file.id} className="relative flex flex-col gap-3 px-4 py-3.5 before:absolute before:inset-x-0 before:top-0 before:ml-4 before:border-t before:border-[var(--surface-divider)] first:before:hidden">
    <WhatsAppHeldFilePreview id={file.id} previewUrl={file.preview_url} mediaType={file.media_type} reading={reading}>
      <span className="block text-base font-normal leading-6">{title}</span>
      <span className={`mt-0.5 block tabular-nums ${muted}`}>
        <time className="max-tablet:block" dateTime={file.held_at}>{t("business.dossier.received", { time: receivedAt(file.held_at, i18n.resolvedLanguage ?? "es-419") })}</time>
        <span className="max-tablet:hidden"> · </span><time className="max-tablet:block" dateTime={file.expires_at}>{expiry(file.expires_at, t)}</time>
      </span>
    </WhatsAppHeldFilePreview>
    {businesses.length > 0 && <div className="flex items-center gap-2">
      {fixed ? <div className="flex min-w-0 flex-1 items-center gap-3"><BusinessIcon /><span className="truncate">{target?.name}</span></div> :
        <BusinessPicker businesses={businesses} selected={target ?? (denied ? chosen : undefined)} disabled={reading || !!busy} onChoose={business => {
          setChosen(business);
          requestAnimationFrame(() => assign.current?.focus());
        }} />}
      <button ref={assign} data-held-control="" type="button" className={`${primaryButtonClass} ${busyHere ? "disabled:opacity-100" : ""}`} disabled={!target || reading || !!busy}
        aria-busy={busyHere} onClick={() => {
          if (!target) return;
          setChosen(target);
          onAssign(file, target);
        }}>
        {busyHere && <LoaderCircle size={16} aria-hidden="true" className="motion-safe:animate-spin" />}{t("settings.whatsapp.held.assign")}
      </button>
    </div>}
    {error && <p role="alert" className="text-sm leading-5 text-[#9e2f39] dark:text-[#ec9aa0]">{t(error)}</p>}
  </li>;
}

export default function WhatsAppHeldFiles({ onBack, onCountChange }: { onBack: () => void; onCountChange: (count: number) => void }) {
  const { t } = useTranslation();
  const business = useContext(BusinessContext);
  const [data, setData] = useState<WhatsAppHeldFilesResponse | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<{ id: string; code: string } | null>(null);
  const request = useRef<AbortController | null>(null);
  const mutation = useRef<AbortController | null>(null);
  const toast = useRef<number | null>(null);
  const body = useRef<HTMLDivElement>(null);
  const focusAfter = useRef<number | null>(null);
  const refresh = useCallback(async () => {
    request.current?.abort();
    const controller = new AbortController();
    request.current = controller;
    try {
      const next = await getWhatsAppHeldFiles(controller.signal);
      if (!controller.signal.aborted) { setData(next); setFailed(false); }
    } catch {
      if (!controller.signal.aborted) setFailed(true);
    }
  }, []);
  const updateCount = useEffectEvent(onCountChange);
  const count = data?.files.length;
  useEffect(() => { if (count !== undefined) updateCount(count); }, [count]);
  useEffect(() => {
    void refresh();
    return () => {
      request.current?.abort();
      mutation.current?.abort();
      if (toast.current !== null) dismissToast(toast.current);
    };
  }, [refresh]);
  const reading = data?.files.some(file => file.reading);
  useEffect(() => {
    if (!reading || busy || failed) return;
    const timer = window.setTimeout(refresh, 3000);
    return () => window.clearTimeout(timer);
  }, [reading, busy, failed, refresh, data]);
  useLayoutEffect(() => {
    if (focusAfter.current === null || busy) return;
    const rows = body.current?.querySelectorAll<HTMLElement>("[data-held-file]");
    const row = rows?.[Math.min(focusAfter.current, rows.length - 1)];
    const target = row?.querySelector<HTMLElement>("[data-held-control]:not(:disabled)") ?? row?.querySelector("button") ?? body.current?.querySelector("h4");
    target?.focus();
    focusAfter.current = null;
  }, [busy, data]);
  async function assign(file: WhatsAppHeldFile, target: Business) {
    if (!data || mutation.current) return;
    request.current?.abort();
    const controller = new AbortController();
    mutation.current = controller;
    setBusy(file.id);
    setProblem(null);
    try {
      await assignWhatsAppHeldFile(file.id, target.space_id, controller.signal);
      if (controller.signal.aborted) return;
      const rowIndex = data.files.findIndex(row => row.id === file.id);
      const row = body.current?.querySelectorAll<HTMLElement>("[data-held-file]")[rowIndex];
      if (row?.animate && !window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
        const collapse = row.animate([
          { height: row.offsetHeight + "px", opacity: 1 },
          { height: "0px", paddingBlock: "0px", transform: "translateX(12px)", opacity: 0 },
        ], { duration: 220, easing: "cubic-bezier(.3,.7,.4,1)", fill: "forwards" });
        row.style.overflow = "hidden";
        await collapse.finished.catch(() => {});
        if (controller.signal.aborted) return;
      }
      focusAfter.current = rowIndex;
      setData(current => current && ({ ...current, files: current.files.filter(row => row.id !== file.id) }));
      toast.current = showToast({ kind: "success", text: t("settings.whatsapp.held.assigned", { business: target.name }) });
    } catch (error) {
      if (controller.signal.aborted) return;
      const code = (error as Partial<WhatsAppLinkError>).code;
      if (code === "business_permission_denied") {
        setProblem({ id: file.id, code });
        setData(current => current && ({ ...current, receiving_businesses: current.receiving_businesses.filter(b => b.space_id !== target.space_id) }));
      } else if (code === "document_busy") {
        setData(current => current && ({ ...current, files: current.files.map(row => row.id === file.id ? { ...row, reading: true } : row) }));
      } else if (code !== "held_file_already_assigned" && code !== "held_file_unavailable") {
        setProblem({ id: file.id, code: "failed" });
      }
      focusAfter.current = data.files.findIndex(row => row.id === file.id);
    } finally {
      // Adopting a draft can settle several held rows that point to the same source.
      if (!controller.signal.aborted) await refresh();
      if (!controller.signal.aborted) setBusy(null);
      mutation.current = null;
    }
  }
  return <div ref={body} className="flex min-h-full flex-col gap-3 px-4 pt-5 pb-4 text-base text-[#172b26] tablet:px-5 tablet:pt-4 tablet:pb-5 dark:text-white">
    {failed && <div role="alert" className="space-y-2"><p>{t("settings.whatsapp.problem_failed")}</p>
      <button type="button" className={secondaryButtonClass} onClick={refresh}>{t("common.retry")}</button></div>}
    {!data && !failed && <p role="status" className={muted}>{t("common.loading")}</p>}
    {data && (data.files.length ? <>
      {data.receiving_businesses.length ? <p className={muted}>{t("settings.whatsapp.held_help")}</p> :
        <p className="rounded-surface bg-[#F7F5EE] p-4 dark:bg-[#1f2225]">{t("settings.whatsapp.setup_title")}</p>}
      <ul className="rounded-surface bg-[#F7F5EE] dark:bg-[#1f2225]" aria-label={t("settings.whatsapp.held_title")}>
        {data.files.map(file => <FileRow key={file.id} file={file} businesses={data.receiving_businesses} busy={busy}
          problem={problem?.id === file.id ? problem.code : undefined} onAssign={assign}/>)}
      </ul>
    </> : <div className="flex flex-1 flex-col items-center justify-center gap-2 p-6 text-center">
      <span className="grid size-11 place-items-center rounded-full bg-[#F7F5EE] dark:bg-[#1f2225]"><Inbox size={22} aria-hidden="true" /></span>
      <h4 className="mt-2 font-medium" tabIndex={-1}>{t("business.inicio.attention.clear_title")}</h4>
      <p className={`max-w-[300px] ${muted}`}>{t("settings.whatsapp.routing_help")}</p>
      <button type="button" className={`mt-2 ${secondaryButtonClass}`} onClick={onBack}>{t("common.back")}</button>
    </div>)}
    {!business && data && createPortal(<ToastViewport />, document.body)}
  </div>;
}
