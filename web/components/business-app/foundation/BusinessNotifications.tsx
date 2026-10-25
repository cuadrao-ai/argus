"use client";

import { useEffect, useId, useRef, useState } from "react";
import Image from "next/image";
import { Bell, Check, CheckCheck, ChevronDown, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BottomSheet from "@/components/ui/BottomSheet";
import { Tooltip } from "@/components/ui/Tooltip";
import { quietButtonClass } from "../business-ui";
import styles from "./business-notifications.module.css";

type Filter = "all" | "unread";
export type NotificationTarget = "equipo" | "correo" | "datos";
type Notice = {
  id: "access" | "channel" | "profile";
  target: NotificationTarget;
  unread: boolean;
  time: "recent" | "earlier" | "yesterday";
};
const SAMPLE_NOTICES: readonly Notice[] = [
  { id: "access", target: "equipo", unread: true, time: "recent" },
  { id: "channel", target: "correo", unread: true, time: "earlier" },
  { id: "profile", target: "datos", unread: false, time: "yesterday" },
];

type Props = {
  businessId?: string;
  businessName?: string;
  preview?: boolean;
  onAction?: (target: NotificationTarget) => void;
};

function NotificationFilter({ value, onChange }: { value: Filter; onChange: (value: Filter) => void }) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const optionsRef = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();
  const options: Filter[] = ["all", "unread"];
  const close = () => { setOpen(false); triggerRef.current?.focus(); };
  useOverlayLayer({
    isOpen: open,
    overlayId: menuId,
    containerRef: rootRef,
    onOutsidePointerDown: () => setOpen(false),
    onKeyDown: (event) => {
      if (event.key === "Escape") { event.preventDefault(); event.stopPropagation(); close(); }
      if (["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) {
        event.preventDefault();
        const current = optionsRef.current.findIndex((button) => button === document.activeElement);
        const next = event.key === "Home" ? 0 : event.key === "End" ? 1 : (current + (event.key === "ArrowUp" ? -1 : 1) + 2) % 2;
        optionsRef.current[next]?.focus();
      }
    },
  });
  useEffect(() => { if (open) optionsRef.current[value === "all" ? 0 : 1]?.focus(); }, [open, value]);
  return <div ref={rootRef} className={styles.filter} onBlur={(event) => {
    if (!event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
  }}>
    <button ref={triggerRef} type="button" className={styles.filterTrigger} aria-label={t("business.notifications.filter")} aria-haspopup="menu" aria-expanded={open} aria-controls={open ? menuId : undefined} onClick={() => setOpen(!open)} onKeyDown={(event) => {
      if (event.key === "ArrowDown" || event.key === "ArrowUp") { event.preventDefault(); setOpen(true); }
    }}>
      {t(`business.notifications.${value}`)}<ChevronDown aria-hidden="true" size={14} className={`${styles.chevron} ${open ? styles.chevronOpen : ""}`} />
    </button>
    {open ? <div id={menuId} role="menu" aria-label={t("business.notifications.filter")} className={styles.filterMenu}>
      {options.map((option, index) => <button key={option} ref={(element) => { optionsRef.current[index] = element; }} type="button" role="menuitemradio" aria-checked={value === option} className={styles.filterOption} onClick={() => { onChange(option); close(); }}>
        {t(`business.notifications.${option}`)}{value === option ? <Check aria-hidden="true" size={16} /> : null}
      </button>)}
    </div> : null}
  </div>;
}

export default function BusinessNotifications({ businessId, businessName, preview = false, onAction }: Props) {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const [filter, setFilter] = useState<Filter>("all");
  const [read, setRead] = useState<Record<string, boolean>>({});
  const [dismissed, setDismissed] = useState<Record<string, boolean>>({});
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);
  const emptyHeadingRef = useRef<HTMLHeadingElement>(null);
  const focusEmptyRef = useRef(false);
  const panelId = useId();
  const titleId = useId();
  const unreadId = useId();
  const title = t("business.notifications.title");
  const keyFor = (notice: Notice) => JSON.stringify([businessId, notice.id]);
  const notices = preview && businessId && process.env.NODE_ENV === "development" && process.env.NEXT_PUBLIC_MOCK_AUTH === "true" ? SAMPLE_NOTICES.filter((notice) => !dismissed[keyFor(notice)]) : [];
  const isUnread = (notice: Notice) => notice.unread && !read[keyFor(notice)];
  const unread = notices.filter(isUnread);
  const visible = filter === "unread" ? unread : notices;
  const state = !notices.length ? "empty-all" : !visible.length ? "empty-unread" : "populated";
  const close = () => { setOpen(false); triggerRef.current?.focus(); };
  useOverlayLayer({
    isOpen: open && !isBelowTablet,
    overlayId: panelId,
    containerRef: rootRef,
    onEscape: close,
    onOutsidePointerDown: () => setOpen(false),
  });
  useEffect(() => { if (open && !isBelowTablet) closeRef.current?.focus(); }, [open, isBelowTablet]);

  useEffect(() => {
    if (state === "empty-all" && focusEmptyRef.current) {
      emptyHeadingRef.current?.focus();
      focusEmptyRef.current = false;
    }
  }, [state]);
  const focusFilter = () => bodyRef.current?.querySelector<HTMLButtonElement>('button[aria-haspopup="menu"]')?.focus();

  const markAll = <Tooltip content={t("business.notifications.mark_all")} side="bottom"><button type="button" aria-label={t("business.notifications.mark_all")} className={`${quietButtonClass} ${styles.markAll}`} disabled={!unread.length} onClick={() => {
    focusFilter();
    setRead((current) => ({ ...current, ...Object.fromEntries(unread.map((notice) => [keyFor(notice), true])) }));
  }}><CheckCheck aria-hidden="true" size={17} /></button></Tooltip>;
  const body = <div ref={bodyRef} className={styles.body}>
    <div className={styles.toolbar}>
      {businessName ? <p className={styles.businessName}>{businessName}</p> : null}
      {notices.length ? <NotificationFilter value={filter} onChange={setFilter} /> : null}
      {isBelowTablet && notices.length ? markAll : null}
    </div>
    <div className={styles.list}>
      {visible.length ? <ul>
        {visible.map((notice) => <li key={notice.id} data-notice={notice.id} className={`${styles.row} ${notice.id === "profile" ? styles.productUpdate : ""}`}>
          <div className={styles.rowHeading}>
            <span className={styles.dotSlot}>{isUnread(notice) ? <span role="img" aria-label={t("business.notifications.unread_label")} className={styles.dot} /> : null}</span>
            <h3 className={isUnread(notice) ? styles.unreadTitle : styles.readTitle}>{t(`business.notifications.samples.${notice.id}.title`)}</h3>
            <span className={styles.timestamp}>{t(`business.notifications.times.${notice.time}`)}</span>
          </div>
          <p className={styles.description}>{t(`business.notifications.samples.${notice.id}.body`, { business: businessName })}</p>
          <div className={styles.rowActions}>
            <button type="button" className={`${quietButtonClass} ${styles.rowAction}`} disabled={!onAction} onClick={() => {
              setRead((current) => ({ ...current, [keyFor(notice)]: true }));
              close();
              onAction?.(notice.target);
            }}>{t(`business.notifications.samples.${notice.id}.action`)}</button>
            <button type="button" className={styles.dismiss} aria-label={t("business.notifications.dismiss", { title: t(`business.notifications.samples.${notice.id}.title`) })} onClick={() => {
              if (notices.length === 1) focusEmptyRef.current = true;
              else focusFilter();
              setDismissed((current) => ({ ...current, [keyFor(notice)]: true }));
            }}><X aria-hidden="true" size={14} /></button>
          </div>
        </li>)}
      </ul> : <div className={styles.empty} data-notification-state={state}>
        <div className={styles.emptyArt}><Image src="/images/notifications/quiet-bell.png" alt="" width={88} height={88} sizes="88px" /></div>
        <h3 ref={emptyHeadingRef} tabIndex={-1} className={styles.emptyTitle}>{t(state === "empty-all" ? "business.notifications.empty_all_title" : "business.notifications.empty_unread_title")}</h3>
        <p className={styles.emptyDescription}>{state === "empty-unread"
          ? t("business.notifications.empty_unread_body")
          : t(businessName ? "business.notifications.empty_all_body_business" : "business.notifications.empty_all_body", { business: businessName })}</p>
        <div className={styles.emptyAction}>{state === "empty-unread" ? <button type="button" className={`${quietButtonClass} ${styles.rowAction}`} onClick={() => { focusFilter(); setFilter("all"); }}>{t("business.notifications.view_all")}</button> : null}</div>
      </div>}
    </div>
  </div>;

  return <div ref={rootRef} className="relative flex items-center" onBlur={(event) => {
    if (!isBelowTablet && event.relatedTarget && !event.currentTarget.contains(event.relatedTarget as Node)) setOpen(false);
  }}>
    <Tooltip content={title} side="bottom">
      <button ref={triggerRef} type="button" data-testid="business-notifications-trigger" aria-label={title} aria-describedby={unread.length ? unreadId : undefined} aria-haspopup="dialog" aria-expanded={open} aria-controls={open && !isBelowTablet ? panelId : undefined} onClick={() => setOpen((value) => !value)} className={`relative flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:bg-[#e3ebe1] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-[#8fcbb0] ${open ? "bg-[#e3ebe1] dark:bg-white/10" : ""}`}>
        <Bell className="h-5 w-5" aria-hidden="true" />
        {unread.length ? <><span aria-hidden="true" className={styles.bellDot} /><span id={unreadId} className="sr-only">{t("business.notifications.unread_count", { count: unread.length })}</span></> : null}
      </button>
    </Tooltip>
    {open && !isBelowTablet ? <div id={panelId} role="dialog" aria-labelledby={titleId} data-testid="business-notifications-popover" className={`${styles.popover} absolute right-0 top-full z-[70] mt-2 rounded-surface border border-[#DCE0DA] bg-[var(--cuadrao-menu-surface)] text-[#172b26] dark:border-white/10 dark:text-white`}>
      <div className={styles.heading}>
        <h2 id={titleId} className="flex-1 text-[16px] font-semibold">{title}</h2>
        {notices.length ? markAll : null}
        <button ref={closeRef} type="button" aria-label={t("common.close")} onClick={close} className={styles.dismiss}><X className="h-4 w-4" aria-hidden="true" /></button>
      </div>
      {body}
    </div> : null}
    {isBelowTablet ? <BottomSheet isOpen={open} onClose={close} title={title} closeLabel={t("common.close")} snaps="fit"><div data-testid="business-notifications-sheet" className={styles.sheetBody}>{open ? body : null}</div></BottomSheet> : null}
  </div>;
}
