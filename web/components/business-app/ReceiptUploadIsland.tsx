"use client";

import { createContext, useCallback, useLayoutEffect, useRef, useState, useSyncExternalStore, type HTMLAttributes, type ReactNode } from "react";
import { flushSync } from "react-dom";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { enteredIn } from "@/lib/business-grant";
import { prefersReducedMotion } from "@/components/ui/spring";
import type { IntakeTarget, ReceiptUploadQueue } from "./receipt-upload-queue";
import { uploadBatchView, uploadSummaryText } from "./receipt-upload-view";
import { exportFailureText, failureOn, useRecordsExportJob } from "./transacciones/records-export-job";
import styles from "./receipt-upload-island.module.css";

export type RecordDrawer = { node: HTMLElement; narrow: boolean };
export const ReportRecordDrawer = createContext<(drawer: RecordDrawer | null) => void>(() => {});

function surfaceFrame(node: HTMLElement) {
  const rect = node.getBoundingClientRect();
  const style = getComputedStyle(node);
  // The used radius of a fully round pill is half its shorter edge.
  const radius = (value: string) => `${Math.min(parseFloat(value) || 0, rect.width / 2, rect.height / 2)}px`;
  return {
    left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`,
    borderTopLeftRadius: radius(style.borderTopLeftRadius),
    borderTopRightRadius: radius(style.borderTopRightRadius),
    borderBottomLeftRadius: radius(style.borderBottomLeftRadius),
    borderBottomRightRadius: radius(style.borderBottomRightRadius),
  };
}

/** Measure both real surfaces across the same commit, including a phone's bottom sheet. */
export function morphUploadPanel(opening: boolean, change: () => void, returnFocus = false) {
  const anchor = document.querySelector<HTMLElement>("[data-upload-anchor]");
  const panel = () => document.querySelector("[data-upload-form]")?.closest<HTMLElement>('[role="dialog"]');
  const island = () => anchor?.querySelector<HTMLElement>("button") ?? anchor;
  const origin = opening ? island() : panel();
  const from = origin && surfaceFrame(origin);
  flushSync(change);
  if (returnFocus) {
    const opener = anchor?.querySelector<HTMLElement>("button:not([inert])") ?? document.querySelector<HTMLElement>("[data-add-primary], [data-testid='business-phone-search']");
    opener?.focus({ preventScroll: true });
  }
  if (!anchor || !from || from.width === "0px" || prefersReducedMotion() || typeof anchor.animate !== "function") {
    return;
  }
  const surface = opening ? panel() : island();
  if (!surface) return;
  // The panel has its own slide when opened from Agregar. The island supplies its entrance here.
  surface.style.animation = "none";
  const to = surfaceFrame(surface);
  const ghost = document.createElement("div");
  ghost.className = styles.morph;
  ghost.dataset.uploadMorph = "";
  ghost.setAttribute("aria-hidden", "true");
  document.body.appendChild(ghost);
  const options = { duration: 380, easing: "cubic-bezier(.32,.9,.3,1)" };
  const motion = ghost.animate([from, to], options);
  const reveal = surface.animate([{ opacity: 0 }, { opacity: 0, offset: 0.9 }, { opacity: 1 }], options);
  const clean = () => { ghost.remove(); reveal.cancel(); };
  motion.onfinish = clean;
  motion.oncancel = clean;
}

const SAVED_MS = 2000;
const EXPORTED_MS = 1600;
/** A job that runs comes before one that failed, and that before one that finished. */
const ORDER = { uploading: 0, preparing: 0, failed: 1, saved: 2, done: 2, idle: 3 } as const;

/** A button when a click opens something. An export being prepared, or just saved, opens nothing. */
function Surface({ open, label, children, ...rest }: { open: (() => void) | null; label: string; children: ReactNode } & HTMLAttributes<HTMLElement> & { inert?: boolean }) {
  if (open) return <button type="button" {...rest} aria-label={label} onClick={open}>{children}</button>;
  return <div {...rest} role={label ? "img" : undefined} aria-label={label || undefined}>{children}</div>;
}

export default function ReceiptUploadIsland({ queue, grant, panelOpen, drawer, phone, onOpen, onOpenExport }: {
  queue: ReceiptUploadQueue;
  grant: string | null;
  panelOpen: boolean;
  drawer: RecordDrawer | null;
  phone?: boolean;
  onOpen: (target: IntakeTarget) => void;
  /** Opens Exportar on the file that failed. */
  onOpenExport: () => void;
}) {
  const { t } = useTranslation();
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter(enteredIn(grant));
  const batch = uploadBatchView(entries, queue.retryWaiting, queue.attempts);
  const exporting = useRecordsExportJob();
  // The open export panel shows its own failure. An export of another Business stays out, as its uploads do.
  const exported = exporting.state.kind === "idle" || (exporting.state.run.panel.scope.grantId ?? null) !== grant || failureOn(exporting.state, exporting.panel) ? null : exporting.state;
  // Of two jobs the one that runs shows, and of two that run, the newer.
  const exportInFront = exported !== null && (ORDER[exported.kind] < ORDER[batch.state] || (ORDER[exported.kind] === ORDER[batch.state] && exported.at >= (batch.state === "saved" ? batch.lastSavedAt : batch.lastAddedAt)));
  const state = exportInFront ? exported.kind : batch.state;
  // A failed export shows the alert icon alone. Its sentence is the name, and Exportar says it in full.
  const words = !exportInFront ? uploadSummaryText(t, batch, "island")
    : exported.kind === "preparing" ? t("business.transactions.reporting.export.preparing") : "";
  const label = !exportInFront ? batch.progress ? t("business.intake.chip_uploading", batch.progress) : words
    : exported.kind === "failed" ? exportFailureText(t, exported.problem, exported.toPlace) : words;
  const open = exportInFront ? exported.kind === "failed" ? onOpenExport : null : () => batch.target && onOpen(batch.target);
  const expires = exportInFront ? exported.kind === "done" ? exported.at + EXPORTED_MS : 0 : batch.state === "saved" ? batch.lastSavedAt + SAVED_MS : 0;
  const subscribeExpiry = useCallback((notify: () => void) => {
    const remaining = expires - Date.now();
    if (remaining <= 0) return () => {};
    const timer = setTimeout(notify, remaining);
    return () => clearTimeout(timer);
  }, [expires]);
  const closing = useSyncExternalStore(subscribeExpiry, () => expires > 0 && Date.now() >= expires, () => false);

  const anchor = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLSpanElement>(null);
  const shown = !panelOpen && state !== "idle" && !(drawer && !drawer.narrow);
  const announcedState = panelOpen || closing ? "idle" : `${exportInFront ? "export" : "upload"} ${state}`;
  const [announcement, setAnnouncement] = useState({ state: "idle", text: "" });
  if (announcement.state !== announcedState) {
    setAnnouncement({ state: announcedState, text: announcedState === "idle" ? "" : label });
  }

  useLayoutEffect(() => {
    const node = anchor.current;
    const search = node?.parentElement;
    if (!node || !search) return;
    const fit = () => {
      const shift = drawer?.narrow ? Math.max(0, search.getBoundingClientRect().left - 8 - drawer.node.getBoundingClientRect().left + 12) : 0;
      node.style.setProperty("--record-shift", `${shift}px`);
      if (content.current) node.style.setProperty("--island-width", `${content.current.offsetWidth + 2}px`);
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(search);
    if (search.parentElement) observer.observe(search.parentElement);
    if (drawer) observer.observe(drawer.node);
    if (content.current) observer.observe(content.current);
    window.addEventListener("resize", fit);
    return () => { observer.disconnect(); window.removeEventListener("resize", fit); };
  }, [drawer, shown, words]);

  return <div ref={anchor} data-upload-anchor="" className={`${styles.anchor} rounded-full`} data-phone={phone || undefined}>
    <span data-upload-announcement="" role="status" className="sr-only">{announcement.text}</span>
    {shown ? <Surface open={open} label={label} data-testid={closing ? undefined : "receipt-upload-island"}
      data-state={state} data-phase={closing ? "closing" : "open"} data-dot={words ? undefined : ""} inert={closing || undefined}
      className={`${styles.island} rounded-full ${state === "failed"
        ? "border-[#e9c4c8] bg-[#f6dfe0] text-[#9e2f39] dark:border-[#ec9aa0]/30 dark:bg-[#4a2a2f] dark:text-[#ec9aa0]"
        : "border-[#C9CFC9] bg-white text-[#172b26] dark:border-white/[0.18] dark:bg-[#1f2225] dark:text-white"}`}>
      <span ref={content} className={styles.content} aria-hidden="true">
        {state === "uploading" ? <svg className={styles.icon} viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8" strokeWidth="2.2" className={styles.track} />
          <circle cx="10" cy="10" r="8" pathLength="1" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
            strokeDasharray="1" strokeDashoffset={1 - batch.fileShare} transform="rotate(-90 10 10)" className={styles.arc} />
          <path d="M10 13.2V7.2M7.4 9.6L10 7l2.6 2.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={styles.arrow} />
        </svg> : state === "preparing" ? <svg className={styles.icon} viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8" strokeWidth="2.2" className={styles.track} />
          <g className={styles.spin}><circle cx="10" cy="10" r="8" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
            strokeDasharray="12 50.27" transform="rotate(-90 10 10)" className={styles.dash} /></g>
          <path data-arrow="down" d="M10 6.8v6M7.4 10.4L10 13l2.6-2.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={styles.arrow} />
        </svg> : state === "failed" ? <CircleAlert size={20} strokeWidth={2.2} /> : <svg className={styles.icon} viewBox="0 0 24 24" fill="none">
          <path pathLength="1" d="M5 12.5l4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" className={styles.check} />
        </svg>}
        {phone || !words ? null : <span>{words}</span>}
      </span>
    </Surface> : null}
  </div>;
}
