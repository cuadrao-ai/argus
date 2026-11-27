"use client";

import { createContext, useCallback, useLayoutEffect, useRef, useState, useSyncExternalStore } from "react";
import { flushSync } from "react-dom";
import { CircleAlert } from "lucide-react";
import { useTranslation } from "react-i18next";
import { enteredIn } from "@/lib/business-grant";
import { prefersReducedMotion } from "@/components/ui/spring";
import type { IntakeTarget, ReceiptUploadQueue } from "./receipt-upload-queue";
import { uploadBatchView, uploadSummaryText } from "./receipt-upload-view";
import styles from "./receipt-upload-island.module.css";

export type RecordDrawer = { node: HTMLElement; narrow: boolean };
export const ReportRecordDrawer = createContext<(drawer: RecordDrawer | null) => void>(() => {});

/** Measure both real surfaces across the same commit, including a phone's bottom sheet. */
export function morphUploadPanel(opening: boolean, change: () => void, returnFocus = false) {
  const anchor = document.querySelector<HTMLElement>("[data-upload-anchor]");
  const panel = () => document.querySelector("[data-upload-form]")?.closest<HTMLElement>('[role="dialog"]');
  const island = () => anchor?.querySelector<HTMLElement>("button") ?? anchor;
  const from = (opening ? island() : panel())?.getBoundingClientRect();
  flushSync(change);
  if (returnFocus) {
    const opener = anchor?.querySelector<HTMLElement>("button:not([inert])") ?? document.querySelector<HTMLElement>("[data-add-primary], [data-testid='business-phone-search']");
    opener?.focus({ preventScroll: true });
  }
  if (!anchor || !from?.width || prefersReducedMotion() || typeof anchor.animate !== "function") {
    return;
  }
  const surface = opening ? panel() : island();
  if (!surface) return;
  // The panel has its own slide when opened from Agregar. The island supplies its entrance here.
  surface.style.animation = "none";
  const to = surface.getBoundingClientRect();
  const ghost = document.createElement("div");
  ghost.className = styles.morph;
  ghost.dataset.uploadMorph = "";
  ghost.setAttribute("aria-hidden", "true");
  document.body.appendChild(ghost);
  const frame = (rect: DOMRect, round: boolean) => ({
    left: `${rect.left}px`, top: `${rect.top}px`, width: `${rect.width}px`, height: `${rect.height}px`,
    borderRadius: round ? "20px" : getComputedStyle(opening ? surface : ghost).borderRadius,
  });
  const options = { duration: 380, easing: "cubic-bezier(.32,.9,.3,1)" };
  const motion = ghost.animate([frame(from, opening), frame(to, !opening)], options);
  const reveal = surface.animate([{ opacity: 0 }, { opacity: 0, offset: 0.9 }, { opacity: 1 }], options);
  const clean = () => { ghost.remove(); reveal.cancel(); };
  motion.onfinish = clean;
  motion.oncancel = clean;
}

export default function ReceiptUploadIsland({ queue, grant, panelOpen, drawer, phone, onOpen }: {
  queue: ReceiptUploadQueue;
  grant: string | null;
  panelOpen: boolean;
  drawer: RecordDrawer | null;
  phone?: boolean;
  onOpen: (target: IntakeTarget) => void;
}) {
  const { t } = useTranslation();
  const entries = useSyncExternalStore(queue.subscribe, queue.snapshot, queue.snapshot).filter(enteredIn(grant));
  const batch = uploadBatchView(entries, queue.retryWaiting, queue.attempts);
  const words = uploadSummaryText(t, batch, "island");
  const label = batch.progress ? t("business.intake.chip_uploading", batch.progress) : words;
  const expires = batch.state === "saved" ? batch.lastSavedAt + 2000 : 0;
  const subscribeExpiry = useCallback((notify: () => void) => {
    const remaining = expires - Date.now();
    if (remaining <= 0) return () => {};
    const timer = setTimeout(notify, remaining);
    return () => clearTimeout(timer);
  }, [expires]);
  const closing = useSyncExternalStore(subscribeExpiry, () => expires > 0 && Date.now() >= expires, () => false);

  const anchor = useRef<HTMLDivElement>(null);
  const content = useRef<HTMLSpanElement>(null);
  const shown = !panelOpen && batch.state !== "idle" && !(drawer && !drawer.narrow);
  const announcedState = panelOpen || closing ? "idle" : batch.state;
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

  return <div ref={anchor} data-upload-anchor="" className={styles.anchor} data-phone={phone || undefined}>
    <span data-upload-announcement="" role="status" className="sr-only">{announcement.text}</span>
    {shown ? <button type="button" data-testid={closing ? undefined : "receipt-upload-island"}
      data-state={batch.state} data-phase={closing ? "closing" : "open"} inert={closing || undefined}
      aria-label={label} onClick={() => batch.target && onOpen(batch.target)}
      className={`${styles.island} ${batch.state === "failed"
        ? "border-[#e9c4c8] bg-[#f6dfe0] text-[#9e2f39] dark:border-[#ec9aa0]/30 dark:bg-[#4a2a2f] dark:text-[#ec9aa0]"
        : "border-[#C9CFC9] bg-white text-[#172b26] dark:border-white/[0.18] dark:bg-[#1f2225] dark:text-white"}`}>
      <span ref={content} className={styles.content} aria-hidden="true">
        {batch.progress ? <svg className={styles.icon} viewBox="0 0 20 20" fill="none">
          <circle cx="10" cy="10" r="8" strokeWidth="2.2" className={styles.track} />
          <circle cx="10" cy="10" r="8" pathLength="1" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round"
            strokeDasharray="1" strokeDashoffset={1 - batch.fileShare} transform="rotate(-90 10 10)" className={styles.arc} />
          <path d="M10 13.2V7.2M7.4 9.6L10 7l2.6 2.6" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" className={styles.arrow} />
        </svg> : batch.state === "saved" ? <svg className={styles.icon} viewBox="0 0 24 24" fill="none">
          <path pathLength="1" d="M5 12.5l4.5 4.5L19 7.5" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" className={styles.check} />
        </svg> : <CircleAlert size={20} strokeWidth={2.2} />}
        {phone ? null : <span>{words}</span>}
      </span>
    </button> : null}
  </div>;
}
