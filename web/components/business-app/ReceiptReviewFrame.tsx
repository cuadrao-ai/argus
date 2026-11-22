"use client";

import { useEffect, useId, useRef, type KeyboardEvent, type ReactNode } from "react";
import { ArrowLeft } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useBusiness } from "./BusinessWorkspace";
import { takeTitleFocus } from "./bandeja-order";
import type { DossierTab } from "./dossier-attention";
import { DossierPlaceNav, DossierSizeButton, type DossierPlace, type JumpRow } from "./dossier/DossierHeader";
import styles from "./dossier/dossier.module.css";
import { TrayFooter, TraySlot, useRecordTray } from "./record-tray";

/** The receipt's place in the list it was opened from, with the moves the list allows now. */
export type ReceiptPlace = DossierPlace;
/** The list's rows for the jump card under "N de M"; absent without a list to jump through. */
export type ReceiptJump = { title: string; rows: readonly JumpRow[] | null; onOpen: () => void; onPick: (id: string) => void };
/** One tab of the dossier. `count` is how many problems wait in it. */
export type DossierTabView = { key: Exclude<DossierTab, "documento">; count?: number; content: ReactNode };

/**
 * The one dossier frame. Its header holds the name and, on line two, the
 * record's status; then its place in the list with the jump card, the size
 * button and the way out. Under it the tabs: General, Datos fiscales, Detalles
 * and Historial on the left, and the document on the right.
 *
 * The frame has two sizes. In the regular one (1040px) the document stays
 * beside the tabs. In the narrow one (640px) the document is the Documento tab.
 * A full page, where a phone shows a record, is always narrow. Every tab stays
 * mounted while another shows, so a form keeps what the person typed. What an
 * action answered belongs to the record, not to a tab: it shows over all of them.
 *
 * Inside the tray the drawer's header is the receipt's: the title names the
 * drawer, and the status and the controls fill its slots. A view with no
 * document of its own (comparing two documents) fills the frame in one column.
 */
export default function ReceiptReviewFrame({ recordId, back, title, status, place, jump, tabs, tab, onTab, notices, document, footer }: {
  recordId: string;
  back: "inbox" | "transactions";
  title: string;
  /** Line two of the header; absent on an accepted record. */
  status?: ReactNode;
  /** Absent without a list to move through. */
  place?: ReceiptPlace | null;
  jump?: ReceiptJump | null;
  tabs: readonly DossierTabView[];
  tab: DossierTab;
  onTab: (tab: DossierTab) => void;
  /** What an action or a refetch answered. It sits over the tabs' content, so it shows whichever tab is open. */
  notices?: ReactNode;
  /** Absent when the view shows its documents itself. */
  document?: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const tray = useRecordTray();
  const ids = useId();
  const heading = useRef<HTMLHeadingElement>(null);
  const setTitle = tray?.setTitle;
  useEffect(() => {
    if (!setTitle) return undefined;
    setTitle(title);
    return () => setTitle(null);
  }, [setTitle, title]);
  useEffect(() => {
    if (!takeTitleFocus(recordId)) return;
    // In the tray the drawer's title is the receipt's.
    (heading.current ?? window.document.getElementById("receipt-review-title"))?.focus();
  }, [recordId]);
  const settleList = tray?.settleList;
  useEffect(() => {
    settleList?.(back);
  }, [settleList, back]);

  const narrow = tray ? tray.narrow === true : true;
  const views: { key: DossierTab; count?: number; content: ReactNode }[] = narrow && document !== undefined
    ? [...tabs.slice(0, 1), { key: "documento", content: document }, ...tabs.slice(1)]
    : [...tabs];
  const current = views.some((view) => view.key === tab) ? tab : views[0]?.key;
  const walk = (event: KeyboardEvent<HTMLDivElement>) => {
    const at = views.findIndex((view) => view.key === current);
    const next = event.key === "ArrowRight" ? at + 1 : event.key === "ArrowLeft" ? at - 1 : null;
    if (next === null) return;
    event.preventDefault();
    const view = views[(next + views.length) % views.length];
    onTab(view.key);
    event.currentTarget.querySelector<HTMLElement>(`[data-tab="${view.key}"]`)?.focus();
  };
  const nav = place ? <DossierPlaceNav place={place} jump={jump ? { ...jump, current: recordId } : null} /> : null;
  const body = (
    <div className={styles.split} data-narrow={narrow || undefined} data-single={document === undefined || undefined} style={tray ? undefined : { height: "auto" }}>
      <div className={styles.info}>
        {views.length > 1 ? <div role="tablist" aria-label={t("business.dossier.tab.label")} data-testid="dossier-tabs" className={styles.tabs} onKeyDown={walk}>
          {views.map((view) => (
            <button key={view.key} type="button" role="tab" id={`${ids}-tab-${view.key}`} data-tab={view.key} aria-selected={view.key === current} aria-controls={`${ids}-panel-${view.key}`} tabIndex={view.key === current ? 0 : -1} className={styles.tab} onClick={() => onTab(view.key)}>
              {t(`business.dossier.tab.${view.key}`)}
              {view.count ? <span className={styles.tabCount} aria-label={t("business.dossier.tab.count", { count: view.count })}>{view.count}</span> : null}
            </button>
          ))}
        </div> : null}
        {notices ? <div className={styles.notices} data-testid="dossier-notices">{notices}</div> : null}
        {views.map((view) => (
          <div key={view.key} role="tabpanel" id={`${ids}-panel-${view.key}`} aria-labelledby={views.length > 1 ? `${ids}-tab-${view.key}` : undefined} hidden={view.key !== current} data-tab-panel={view.key} data-document={view.key === "documento" || undefined} data-testid={view.key === "general" ? "receipt-review-fields" : view.key === "historial" ? "receipt-review-history" : `dossier-panel-${view.key}`} className={styles.panel}>
            {view.key === "documento" ? view.content : <div className={styles.stack}>{view.content}</div>}
          </div>
        ))}
      </div>
      {!narrow && document !== undefined ? document : null}
    </div>
  );
  if (tray) {
    return (
      <section aria-labelledby="receipt-review-title" data-testid="business-record-review" data-presentation="tray" data-size={narrow ? "narrow" : "regular"} className={`${styles.scope} absolute inset-0`}>
        {status ? <TraySlot slot="summary">{status}</TraySlot> : null}
        <TraySlot slot="headerActions"><div className="flex items-center gap-2">{nav}<DossierSizeButton /></div></TraySlot>
        {body}
        {footer ? <TrayFooter><div data-testid="receipt-review-footer">{footer}</div></TrayFooter> : null}
      </section>
    );
  }
  return (
    <section aria-labelledby="receipt-review-title" data-testid="business-record-review" data-presentation="page" data-size="narrow" className={styles.scope}>
      {/* Opaque, and its shadow fills the see-through app bar above it, so the form never shows through either while it scrolls under. */}
      <header className="sticky top-0 z-20 -mx-4 border-b border-[#DCE0DA] bg-[#F7F5EE] px-4 pb-3 pt-2 shadow-[0_-6rem_0_0_#F7F5EE] tablet:-mx-8 tablet:px-8 dark:border-white/10 dark:bg-[#141517] dark:shadow-[0_-6rem_0_0_#141517]">
        <div className="flex items-center justify-between gap-2">
          <button type="button" onClick={() => openPanel({ kind: back })} className="flex min-h-11 items-center gap-2 rounded-full pr-3 text-[15px] text-[#56635e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70">
            <ArrowLeft className="h-5 w-5" aria-hidden="true" />
            {back === "transactions" ? t("business.nav.transactions", "Transactions") : t("business.nav.inbox", "Inbox")}
          </button>
          {nav}
        </div>
        <h2 id="receipt-review-title" ref={heading} tabIndex={-1} className="mt-1 min-w-0 break-words rounded-mark font-display text-[22px] font-medium leading-7 text-[#172b26] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white">{title}</h2>
        {status ? <div className="mt-1">{status}</div> : null}
      </header>
      <div className="-mx-4 tablet:-mx-8">{body}</div>
      {footer ? (
        // The workspace region pads its bottom by 48px and sticky offsets count from inside that padding; -48px on both puts the footer on the pane's edge.
        <div data-testid="receipt-review-footer" className="sticky bottom-[-48px] z-10 -mx-4 -mb-12 border-t border-[#DCE0DA] bg-[#FFFEFA] px-4 py-3 tablet:-mx-8 tablet:px-6 dark:border-white/10 dark:bg-[#1f2225]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}
