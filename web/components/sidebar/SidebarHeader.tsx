"use client";

import { useEffect, useState, type ReactNode } from "react";
import { PanelLeft, X } from "lucide-react";
import { SidebarSimple } from "@phosphor-icons/react";
import { useTranslation } from "react-i18next";
import { CuadraoMark } from "@/components/CuadraoMark";
import { Tooltip } from "@/components/ui/Tooltip";

export type SidebarVariant = "rail" | "drawer";

/** The rail's width transition (ChatSidebar's duration-200). */
const RAIL_CLOSE_MS = 200;

export default function SidebarHeader({
  variant,
  isOpen,
  railLocked = false,
  business = false,
  businessSlot,
  businessMark,
  onToggle,
  onRequestClose,
}: {
  variant: SidebarVariant;
  isOpen: boolean;
  railLocked?: boolean;
  business?: boolean;
  /** Business only: the business card takes the brand's place at the top; the brand moves to the foot of the rail. */
  businessSlot?: ReactNode;
  /** The business's mark: on a closed rail it is the expand button, as the brand mark was. */
  businessMark?: ReactNode;
  onToggle: () => void;
  onRequestClose?: () => void;
}) {
  const { t } = useTranslation();
  const brandName = "cuadrao";
  // The open header stays through the rail's 200ms close, clipped by the narrowing rail, then gives way to the closed one.
  const [shownOpen, setShownOpen] = useState(isOpen);
  useEffect(() => {
    if (isOpen) {
      setShownOpen(true);
      return undefined;
    }
    const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
    if (reduced) {
      setShownOpen(false);
      return undefined;
    }
    const timer = window.setTimeout(() => setShownOpen(false), RAIL_CLOSE_MS);
    return () => window.clearTimeout(timer);
  }, [isOpen]);
  const brandMark = (drawer = false) => (
    <CuadraoMark size={32} className="h-8 w-8 shrink-0" testId={drawer ? "sidebar-drawer-logo" : undefined} />
  );

  if (variant === "drawer") {
    return (
      <div className="flex h-20 items-center justify-between gap-2 px-3 pb-4 pt-6">
        <div className="flex min-w-0 items-center gap-2">
          {brandMark(true)}
          <span className="font-display truncate text-[22px] font-medium tracking-tight text-black dark:text-white">
            {brandName}
          </span>
        </div>
        <button
          type="button"
          onClick={onRequestClose}
          data-testid="sidebar-drawer-close"
          aria-label={t("sidebar.close", "Close sidebar")}
          className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:hover:bg-white/5 dark:focus-visible:ring-white/30"
        >
          <X className="h-5 w-5 text-black/60 dark:text-white/60" aria-hidden="true" />
        </button>
      </div>
    );
  }

  if (railLocked && business && businessSlot) {
    return <div className="flex h-14 shrink-0 items-center justify-center">{businessSlot}</div>;
  }


  if (railLocked) {
    return (
      <div className="flex h-14 shrink-0 items-center justify-center">
        {brandMark()}
        <span className="sr-only">{brandName}</span>
      </div>
    );
  }

  const toggle = (
    <Tooltip
      content={isOpen ? t("sidebar.close", "Close sidebar") : t("sidebar.open", "Open sidebar")}
      side="right"
    >
      <button
        type="button"
        onClick={onToggle}
        data-testid="sidebar-rail-toggle"
        className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-[12px] transition-colors duration-200 hover:bg-black/5 dark:hover:bg-white/5"
        aria-label={isOpen ? t("common.collapse", "Collapse") : t("common.expand", "Expand")}
      >
        {isOpen ? <PanelLeft className="h-5 w-5 text-black/60 dark:text-white/60" /> : brandMark()}
      </button>
    </Tooltip>
  );

  if (business && businessSlot) {
    const railToggle = (
      <Tooltip content={isOpen ? t("sidebar.close", "Close sidebar") : t("sidebar.open", "Open sidebar")} side="right">
        <button
          type="button"
          onClick={onToggle}
          data-testid="sidebar-rail-toggle"
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full text-black/60 transition-colors duration-200 hover:bg-black/5 dark:text-white/60 dark:hover:bg-white/5"
          aria-label={isOpen ? t("common.collapse", "Collapse") : t("common.expand", "Expand")}
        >
          <SidebarSimple size={20} aria-hidden="true" />
        </button>
      </Tooltip>
    );
    // Both layouts put the mark at the same spot, and the open one stays while the rail closes, so nothing jumps.
    if (shownOpen) {
      return (
        <div className="flex h-14 shrink-0 items-center gap-1 overflow-hidden pl-[10px] pr-1 pt-2">
          <div className="min-w-0 flex-1">{businessSlot}</div>
          {railToggle}
        </div>
      );
    }
    // Closed, the business's mark is the way back open: hovering or focusing it shows the expand icon in its place.
    return (
      <div className="flex h-14 shrink-0 items-center pl-[10px] pt-2">
        <Tooltip content={t("sidebar.open", "Open sidebar")} side="right">
          <button
            type="button"
            onClick={onToggle}
            data-testid="sidebar-rail-toggle"
            aria-label={t("common.expand", "Expand")}
            className="group relative flex h-11 w-11 items-center justify-center rounded-item transition-colors duration-200 hover:bg-black/5 focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:hover:bg-white/5"
          >
            <span className="transition-opacity duration-150 ease-out group-hover:opacity-0 group-focus-visible:opacity-0">{businessMark ?? brandMark()}</span>
            <SidebarSimple size={20} className="absolute text-black/60 opacity-0 transition-opacity duration-150 ease-out group-hover:opacity-100 group-focus-visible:opacity-100 dark:text-white/60" aria-hidden="true" />
          </button>
        </Tooltip>
      </div>
    );
  }

  if (business) {
    return isOpen ? (
      <div className="flex h-14 shrink-0 items-center gap-3 pl-3 pr-1">
        {brandMark()}
        <span className="min-w-0 flex-1 truncate font-display text-[22px] font-medium tracking-tight text-black dark:text-white">
          {brandName}
        </span>
        {toggle}
      </div>
    ) : (
      <div className="flex h-14 shrink-0 items-center justify-center">{toggle}</div>
    );
  }

  return (
    <div className="flex h-20 items-center px-[6px] pb-4 pt-6">
      <Tooltip
        content={isOpen ? t("sidebar.close", "Close sidebar") : t("sidebar.open", "Open sidebar")}
        side="right"
      >
        <button
          onClick={onToggle}
          className="flex h-11 w-11 flex-shrink-0 items-center justify-center rounded-full transition-all duration-200 hover:bg-black/5 dark:hover:bg-white/5 active:scale-95"
          aria-label={isOpen ? t("common.collapse", "Collapse") : t("common.expand", "Expand")}
        >
          {isOpen ? (
            <PanelLeft className="h-5 w-5 text-black/60 dark:text-white/60" />
          ) : (
            brandMark()
          )}
        </button>
      </Tooltip>
      <span
        className={`ml-1 whitespace-nowrap font-display text-[22px] font-medium tracking-tight text-black transition-[opacity,max-width] duration-300 ease-in-out dark:text-white ${
          isOpen ? "max-w-[200px] opacity-100" : "max-w-0 overflow-hidden opacity-0"
        }`}
      >
        {brandName}
      </span>
    </div>
  );
}
