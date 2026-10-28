"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { ArrowLeft, ChevronDown, ChevronUp } from "lucide-react";
import { useTranslation } from "react-i18next";
import { SegmentedControl } from "@/components/ui/SegmentedControl";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useBusiness } from "./BusinessWorkspace";
import { takeTitleFocus } from "./bandeja-order";
import { CHANNEL_ICON } from "./foundation/channel-icons";
import { formatTimestamp } from "./business-format";
import { TrayFooter, TraySlot, useRecordTray } from "./record-tray";
import { resolveLanguage } from "@/lib/language-features";

/** Where the record came from, as its first source says: the channel is the source's own. */
export type ReceiptOrigin = { channel: keyof typeof CHANNEL_ICON; receivedAt: string; message?: boolean };

/** The receipt's place in the list it was opened from, with the moves the list allows now. */
export type ReceiptPlace = { index: number; total: number; previous?: () => void; next?: () => void };

function OriginLine({ origin }: { origin: ReceiptOrigin }) {
  const { t, i18n } = useTranslation();
  const Icon = CHANNEL_ICON[origin.channel];
  const label = origin.channel === "whatsapp" ? "WhatsApp"
    : origin.channel === "email" ? t("business.history.channel_email", "Email")
    : origin.message ? t("business.dossier.web_message", "Web message")
    : t("business.history.channel_web", "Uploaded");
  return (
    <p data-testid="receipt-origin" className="mt-1 flex items-center gap-1.5 text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">
      <Icon size={15} aria-hidden="true" className="shrink-0" />
      <span>{label} · {formatTimestamp(origin.receivedAt, i18n.resolvedLanguage ?? resolveLanguage({}))}</span>
    </p>
  );
}

function PlaceNav({ place }: { place: ReceiptPlace }) {
  const { t } = useTranslation();
  const button = "flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/65 hover:bg-black/5 disabled:opacity-35 disabled:hover:bg-transparent focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10";
  return (
    <div data-testid="receipt-place" className="flex items-center">
      <span className="mr-1 whitespace-nowrap text-[13px] tabular-nums text-[#56635e] dark:text-white/70">{t("business.dossier.place", { index: place.index, total: place.total, defaultValue: "{{index}} of {{total}}" })}</span>
      <button type="button" className={button} disabled={!place.previous} onClick={place.previous} aria-label={t("business.shortcuts.previous_receipt", "Previous receipt")}><ChevronUp className="h-5 w-5" aria-hidden="true" /></button>
      <button type="button" className={button} disabled={!place.next} onClick={place.next} aria-label={t("business.shortcuts.next_receipt", "Next receipt")}><ChevronDown className="h-5 w-5" aria-hidden="true" /></button>
    </div>
  );
}

/**
 * The one receipt review page. One header holds the supplier, the total, the
 * status, where it came from and its place in the list; then the form and the
 * original. Every state of a receipt renders inside this frame.
 *
 * Inside the tray (the wide dossier drawer) the header is the drawer's own:
 * the receipt names the drawer and fills its summary and its controls, and the
 * footer goes to the drawer's pinned footer. A wide drawer puts the form and
 * its history on the left and the original on the right, held in view while
 * the form scrolls. On a full page the header sticks to the top, and below the
 * tablet stop the form and the original are two tabs.
 */
export default function ReceiptReviewFrame({ recordId, back, title, badge, amount, mark, origin, place, source, children, history, footer }: {
  recordId: string;
  back: "inbox" | "transactions";
  title: string;
  badge?: ReactNode;
  /** The formatted total; absent while it is unknown, never a zero. */
  amount?: string | null;
  mark?: string | null;
  origin?: ReceiptOrigin | null;
  /** Absent without a list to move through. */
  place?: ReceiptPlace | null;
  source: ReactNode;
  children: ReactNode;
  /** Under the fields on a desktop; last of all on a phone. */
  history?: ReactNode;
  footer?: ReactNode;
}) {
  const { t } = useTranslation();
  const { openPanel } = useBusiness();
  const tray = useRecordTray();
  const { isBelowTablet } = useResponsiveLayout();
  const [tab, setTab] = useState<"form" | "original">("form");
  const heading = useRef<HTMLHeadingElement>(null);
  const setTitle = tray?.setTitle;
  const presentation = tray ? "tray" : "page";
  useEffect(() => {
    if (!setTitle) return undefined;
    setTitle(title);
    return () => setTitle(null);
  }, [setTitle, title]);
  useEffect(() => {
    if (!takeTitleFocus(recordId)) return;
    // In the tray the drawer's title is the receipt's.
    (heading.current ?? document.getElementById("receipt-review-title"))?.focus();
  }, [recordId]);
  const settleList = tray?.settleList;
  useEffect(() => {
    settleList?.(back);
  }, [settleList, back]);
  const meta = (
    <div data-testid="receipt-top-block">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        {amount ? <span data-testid="receipt-total" className="cuadrao-amount text-[20px] font-medium leading-7 tabular-nums text-[#172b26] dark:text-white">{amount}</span> : null}
        {badge}
        {mark ? <span data-testid="bill-mark" className="text-[13px] leading-[18px] text-[#56635e] dark:text-white/70">{mark}</span> : null}
      </div>
      {origin ? <OriginLine origin={origin} /> : null}
    </div>
  );
  if (presentation === "tray") {
    return (
      <section aria-labelledby="receipt-review-title" data-testid="business-record-review" data-presentation="tray" className="@container">
        <TraySlot slot="summary">{meta}</TraySlot>
        {place ? <TraySlot slot="headerActions"><PlaceNav place={place} /></TraySlot> : null}
        <div className="grid gap-6 @[52rem]:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] @[52rem]:items-start">
          <div className="min-w-0 space-y-4 @[52rem]:sticky @[52rem]:top-0 @[52rem]:col-start-2 @[52rem]:row-span-2 @[52rem]:row-start-1 @[52rem]:max-h-[calc(100dvh-13rem)] @[52rem]:overflow-y-auto" data-testid="receipt-review-source">{source}</div>
          <div className="min-w-0 space-y-5 @[52rem]:col-start-1 @[52rem]:row-start-1" data-testid="receipt-review-fields">{children}</div>
          {history ? <div className="min-w-0 empty:hidden @[52rem]:col-start-1 @[52rem]:row-start-2" data-testid="receipt-review-history">{history}</div> : null}
        </div>
        {footer ? <TrayFooter><div data-testid="receipt-review-footer">{footer}</div></TrayFooter> : null}
      </section>
    );
  }
  const tabs = isBelowTablet;
  return (
    <section aria-labelledby="receipt-review-title" data-testid="business-record-review" data-presentation="page">
      {/* Opaque, and its shadow fills the see-through app bar above it, so the form never shows through either while it scrolls under. */}
      <header className="sticky top-0 z-20 -mx-4 mb-4 border-b border-[#DCE0DA] bg-[#F7F5EE] px-4 pb-3 pt-2 shadow-[0_-6rem_0_0_#F7F5EE] tablet:-mx-8 tablet:px-8 dark:border-white/10 dark:bg-[#141517] dark:shadow-[0_-6rem_0_0_#141517]">
        <div className="flex items-center justify-between gap-2">
          <button type="button" onClick={() => openPanel({ kind: back })} className="flex min-h-11 items-center gap-2 rounded-full pr-3 text-[15px] text-[#56635e] focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white/70">
            <ArrowLeft className="h-5 w-5" aria-hidden="true" />
            {back === "transactions" ? t("business.nav.transactions", "Transactions") : t("business.nav.inbox", "Inbox")}
          </button>
          {place ? <PlaceNav place={place} /> : null}
        </div>
        <h2 id="receipt-review-title" ref={heading} tabIndex={-1} className="mt-1 min-w-0 break-words rounded-mark font-display text-[22px] font-medium leading-7 text-[#172b26] focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white">{title}</h2>
        <div className="mt-1">{meta}</div>
        {tabs ? (
          <div className="mt-3">
            <SegmentedControl
              testId="receipt-review-tabs"
              label={t("business.dossier.view_label", "View")}
              segments={[{ key: "form" as const, label: t("business.dossier.tab_form", "Form") }, { key: "original" as const, label: t("business.dossier.tab_original", "Original") }]}
              value={tab}
              onChange={setTab}
            />
          </div>
        ) : null}
      </header>
      <div className="grid items-start gap-4 desktop:grid-cols-[minmax(280px,1fr)_minmax(0,640px)] desktop:grid-rows-[auto_1fr] desktop:gap-6">
        <div hidden={tabs && tab !== "form"} className="min-w-0 space-y-5 desktop:col-start-2 desktop:row-start-1" data-testid="receipt-review-fields">{children}</div>
        <div hidden={tabs && tab !== "original"} className="min-w-0 space-y-4 desktop:col-start-1 desktop:row-span-2 desktop:row-start-1 desktop:space-y-6" data-testid="receipt-review-source">{source}</div>
        {history ? <div hidden={tabs && tab !== "form"} className="min-w-0 empty:hidden desktop:col-start-2 desktop:row-start-2" data-testid="receipt-review-history">{history}</div> : null}
      </div>
      {footer ? (
        // The workspace region pads its bottom by 48px and sticky offsets count from inside that padding; -48px on both puts the footer on the pane's edge.
        <div data-testid="receipt-review-footer" className="sticky bottom-[-48px] z-10 -mx-4 -mb-12 mt-6 border-t border-[#DCE0DA] bg-[#FFFEFA] px-4 py-3 tablet:-mx-8 tablet:px-6 dark:border-white/10 dark:bg-[#1f2225]">
          {footer}
        </div>
      ) : null}
    </section>
  );
}
