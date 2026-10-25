"use client";

import { useEffect, useId, useRef, useState } from "react";
import { Bell, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useOverlayLayer } from "@/components/layout/overlayStack";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import BottomSheet from "@/components/ui/BottomSheet";
import { Tooltip } from "@/components/ui/Tooltip";
import styles from "./business-notifications.module.css";

export default function BusinessNotifications() {
  const { t } = useTranslation();
  const { isBelowTablet } = useResponsiveLayout();
  const [open, setOpen] = useState(false);
  const rootRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();
  const titleId = useId();
  const title = t("business.notifications.title");
  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  useOverlayLayer({
    isOpen: open && !isBelowTablet,
    overlayId: panelId,
    containerRef: rootRef,
    onEscape: close,
    onOutsidePointerDown: () => setOpen(false),
  });
  useEffect(() => {
    if (open && !isBelowTablet) closeRef.current?.focus();
  }, [open, isBelowTablet]);

  const body = (
    <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/65">
      {t("business.notifications.body")}
    </p>
  );

  return (
    <div ref={rootRef} className="relative flex items-center" onBlur={(event) => {
      if (!isBelowTablet && !event.currentTarget.contains(event.relatedTarget as Node | null)) setOpen(false);
    }}>
      <Tooltip content={title} side="bottom">
        <button
          ref={triggerRef}
          type="button"
          data-testid="business-notifications-trigger"
          aria-label={title}
          aria-haspopup="dialog"
          aria-expanded={open}
          aria-controls={open && !isBelowTablet ? panelId : undefined}
          onClick={() => setOpen((value) => !value)}
          className={`flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:bg-[#e3ebe1] hover:text-[#172b26] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/70 dark:hover:bg-white/10 dark:hover:text-white dark:focus-visible:outline-[#8fcbb0] ${open ? "bg-[#e3ebe1] dark:bg-white/10" : ""}`}
        >
          <Bell className="h-5 w-5" aria-hidden="true" />
        </button>
      </Tooltip>
      {open && !isBelowTablet ? (
        <div id={panelId} role="dialog" aria-labelledby={titleId} data-testid="business-notifications-popover" className={`${styles.popover} absolute right-0 top-full z-[70] mt-2 rounded-surface border border-[#DCE0DA] bg-[var(--cuadrao-menu-surface)] text-[#172b26] dark:border-white/10 dark:text-white`}>
          <div className={`${styles.heading} flex items-center justify-between`}>
            <h2 id={titleId} className="text-[16px] font-semibold">{title}</h2>
            <button ref={closeRef} type="button" aria-label={t("common.close")} onClick={close} className={`${styles.close} flex h-11 w-11 items-center justify-center rounded-full text-[#56635e] transition-colors hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#2f5a49] dark:text-white/65 dark:hover:bg-white/10 dark:focus-visible:outline-[#8fcbb0]`}>
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
          {body}
        </div>
      ) : null}
      {isBelowTablet ? (
        <BottomSheet isOpen={open} onClose={close} title={title} closeLabel={t("common.close")} snaps="fit">
          <div data-testid="business-notifications-sheet" className={styles.sheetBody}>{body}</div>
        </BottomSheet>
      ) : null}
    </div>
  );
}
