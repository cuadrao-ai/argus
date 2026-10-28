"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useEffect, useId, useRef, type ReactNode } from "react";
import { ChevronLeft, Maximize2, Minimize2, X } from "lucide-react";
import { useTranslation } from "react-i18next";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import { useModalSurface } from "@/components/layout/useModalSurface";
import BottomSheet, { type SheetSnap } from "@/components/ui/BottomSheet";
import { useSheetStack } from "@/components/ui/sheetStack";
import styles from "./adaptive-panel.module.css";

/**
 * The one sheet: for anything done while the page stays in view (a form, a
 * picker, a list, a record's details). Below the desktop stop it is a bottom
 * sheet that rests at its snap points. From the desktop stop it is a side
 * drawer on the right, between 320px and 40% of the screen, so the page stays
 * readable beside it; a record beside its list is a wider, non-modal tray.
 * A full stop (delete, close a month) is not a sheet: it is a ConfirmDialog.
 *
 * Owning the header matters as much as owning the shape. It is what lets a
 * child panel offer a back row instead of a close, so opening Appearance from
 * Preferences returns you to Preferences rather than dismissing everything.
 */

export type AdaptivePanelWidth = "sm" | "md" | "lg" | "record";

type PanelExpansion = { expanded: boolean; onToggle: () => void; expandLabel: string; collapseLabel: string };

type DrawerBounds = { preferred: number; min: number; maxVw: number };

/**
 * The drawer's preferred width and its bounds. A record holds its receipt
 * image and its fields in one column beside a list that needs only its rows,
 * so it may take half the screen; everything else stays under 40%.
 */
const DRAWER_WIDTH: Record<AdaptivePanelWidth, DrawerBounds> = {
  sm: { preferred: 360, min: 320, maxVw: 40 },
  md: { preferred: 420, min: 320, maxVw: 40 },
  lg: { preferred: 560, min: 320, maxVw: 40 },
  record: { preferred: 640, min: 420, maxVw: 50 },
};

export default function AdaptivePanel({
  title,
  titleIcon,
  summary,
  headerSize = "default",
  onClose,
  onBack,
  backLabel,
  closeLabel,
  dismissible = true,
  modal = true,
  width = "sm",
  snaps = ["half", "full"],
  initialSnap,
  footer,
  returnFocusRef,
  initialFocusRef,
  expansion,
  children,
}: {
  title: string;
  /** A small mark before the title, such as a channel's logo; decorative, the title names the panel. */
  titleIcon?: ReactNode;
  /** One line under the title; on a phone it is what the peek snap shows. */
  summary?: ReactNode;
  headerSize?: "default" | "large";
  onClose: () => void;
  /** Present on a child panel; returns to the parent instead of dismissing. */
  onBack?: () => void;
  backLabel?: string;
  closeLabel: string;
  dismissible?: boolean;
  /**
   * False for a record beside its list: no overlay, no focus trap, and the
   * page stays usable. Escape inside it and its close control still close it.
   * Only the side drawer has this mode; a bottom sheet is always modal.
   */
  modal?: boolean;
  width?: AdaptivePanelWidth;
  expansion?: PanelExpansion;
  /** The bottom sheet's snap points on a phone. */
  snaps?: readonly SheetSnap[];
  initialSnap?: SheetSnap;
  footer?: ReactNode;
  /** Where focus lands on close when the opener has gone with the parent. */
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  /**
   * Where focus lands on open, for a panel whose first job is typing.
   *
   * Both presentations otherwise start on the close control, so a panel that
   * marked a field `autoFocus` lost it: the attribute runs during commit and
   * the surface's own focus effect moves focus afterwards.
   */
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  children: ReactNode;
}) {
  const { t } = useTranslation();
  const { isBelowDesktop } = useResponsiveLayout();
  const overlayId = useId();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const stackBackLabel = t("common.back", "Back");

  const back = onBack ? (
    <button
      type="button"
      onClick={onBack}
      className="flex min-h-11 w-full items-center gap-1.5 px-4 text-left text-[13px] text-[#56635e] transition-colors hover:text-black dark:text-white/70 dark:hover:text-white"
    >
      <ChevronLeft className="h-3.5 w-3.5" aria-hidden="true" />
      {backLabel}
    </button>
  ) : null;

  if (isBelowDesktop) {
    return (
      <BottomSheet
        isOpen
        onClose={onClose}
        dismissible={dismissible}
        title={title}
        titleIcon={titleIcon}
        description={summary}
        headerSize={headerSize}
        closeLabel={closeLabel}
        backLabel={stackBackLabel}
        snaps={snaps}
        initialSnap={initialSnap}
        footer={footer}
        initialFocusRef={initialFocusRef}
      >
        {back}
        {children}
      </BottomSheet>
    );
  }

  return <SideDrawer {...{ title, titleIcon, summary, headerSize, titleId, overlayId, panelRef, onClose, closeLabel, stackBackLabel, dismissible, modal, width, footer, returnFocusRef, initialFocusRef, back, expansion, children }} />;
}

const EXPANDED_WIDTH: DrawerBounds = { preferred: 1200, min: 720, maxVw: 88 };

/** While the drawer is drawn, the page gives up its width so it stays readable beside it. */
/**
 * Every drawn drawer claims the room it needs; the page gives up the widest
 * claim. A drawer stacked on another hands its claim over without the page
 * snapping back between them.
 */
const drawerClaims = new Map<string, number>();
function applyDrawerSpace() {
  const root = document.documentElement;
  if (drawerClaims.size) root.style.setProperty("--cuadrao-drawer-space", `${Math.max(...drawerClaims.values())}px`);
  else root.style.removeProperty("--cuadrao-drawer-space");
}

function useDrawerSpace(id: string, { preferred, min, maxVw }: DrawerBounds, drawn: boolean) {
  useEffect(() => {
    if (!drawn) return undefined;
    const claim = () => {
      drawerClaims.set(id, Math.max(min, Math.min(preferred, (window.innerWidth * maxVw) / 100)));
      applyDrawerSpace();
    };
    claim();
    window.addEventListener("resize", claim);
    return () => {
      window.removeEventListener("resize", claim);
      drawerClaims.delete(id);
      applyDrawerSpace();
    };
  }, [id, preferred, min, maxVw, drawn]);
}

type DrawerProps = {
  title: string;
  titleIcon?: ReactNode;
  summary?: ReactNode;
  headerSize: "default" | "large";
  titleId: string;
  overlayId: string;
  panelRef: React.RefObject<HTMLDivElement | null>;
  onClose: () => void;
  closeLabel: string;
  stackBackLabel: string;
  dismissible: boolean;
  modal: boolean;
  width: AdaptivePanelWidth;
  expansion?: PanelExpansion;
  footer?: ReactNode;
  returnFocusRef?: React.RefObject<HTMLElement | null>;
  initialFocusRef?: React.RefObject<HTMLElement | null>;
  back: ReactNode;
  children: ReactNode;
};

type StackPlace = { drawn: boolean; hasBelow: boolean };

function SideDrawerSurface(props: DrawerProps) {
  const place = useSheetStack(props.overlayId, true);
  useDrawerSpace(props.overlayId, DRAWER_WIDTH[props.width], place.drawn);
  return props.modal ? <ModalDrawer {...props} {...place} /> : <TrayDrawer {...props} {...place} />;
}

function ModalDrawer(props: DrawerProps & StackPlace) {
  const { overlayId, panelRef, onClose, closeLabel, dismissible, returnFocusRef, initialFocusRef, drawn, hasBelow } = props;
  useModalSurface({
    isOpen: true,
    overlayId,
    containerRef: panelRef,
    onDismiss: onClose,
    canDismiss: () => dismissible,
    onEscape: dismissible ? onClose : () => {},
    returnFocusRef,
    initialFocusRef,
  });
  return (
    <div className="fixed inset-0 z-[70]" hidden={!drawn} data-sheet-stacked={hasBelow ? "true" : undefined}>
      {/* The page stays in view: no dimming, no blur. A click beside the drawer closes it. */}
      <button type="button" tabIndex={-1} className="absolute inset-0 cursor-default" onClick={dismissible ? onClose : undefined} aria-label={closeLabel} />
      <DrawerPanel {...props} className="absolute inset-y-0 right-0" role="dialog" />
    </div>
  );
}

/** The page beside it keeps its clicks and its Tab order; the owner returns focus on close. */
function TrayDrawer(props: DrawerProps & StackPlace) {
  const { onClose, dismissible, initialFocusRef, drawn } = props;
  const titleRef = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    (initialFocusRef?.current ?? titleRef.current)?.focus();
  }, [initialFocusRef]);
  return (
    <DrawerPanel
      {...props}
      titleRef={titleRef}
      hidden={!drawn}
      className="fixed inset-y-0 right-0 z-[70]"
      role="region"
      onKeyDown={(event) => {
        if (event.key !== "Escape" || event.defaultPrevented || !dismissible) return;
        event.preventDefault();
        onClose();
      }}
    />
  );
}

function DrawerPanel({
  title,
  titleIcon,
  summary,
  headerSize,
  titleId,
  panelRef,
  onClose,
  closeLabel,
  stackBackLabel,
  dismissible,
  width,
  expansion,
  footer,
  back,
  children,
  hasBelow,
  className,
  role,
  hidden,
  titleRef,
  onKeyDown,
}: DrawerProps & StackPlace & {
  className: string;
  role: "dialog" | "region";
  hidden?: boolean;
  titleRef?: React.RefObject<HTMLHeadingElement | null>;
  onKeyDown?: React.KeyboardEventHandler<HTMLDivElement>;
}) {
  const bounds = expansion?.expanded ? EXPANDED_WIDTH : DRAWER_WIDTH[width];
  return (
    <div
      ref={panelRef}
      role={role}
      aria-modal={role === "dialog" ? "true" : undefined}
      aria-labelledby={titleId}
      data-testid="side-drawer"
      data-expanded={expansion ? expansion.expanded : undefined}
      hidden={hidden}
      onKeyDown={onKeyDown}
      style={{ width: `min(${bounds.preferred}px, ${bounds.maxVw}vw)`, minWidth: `${bounds.min}px` }}
      className={`${className} ${styles.dossier} flex flex-col border-l border-[#DCE0DA] bg-white dark:border-white/10 dark:bg-[#1b1d20] ${hasBelow ? "" : "cuadrao-side-drawer-enter"}`}
    >
      <div className="flex shrink-0 items-start gap-2 border-b border-[#DCE0DA] px-5 py-4 dark:border-white/10">
        {hasBelow && dismissible ? (
          <button
            type="button"
            onClick={onClose}
            aria-label={stackBackLabel}
            className="-ml-2 flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/70 hover:bg-black/5 dark:text-white/70 dark:hover:bg-white/10"
          >
            <ChevronLeft className="h-5 w-5" aria-hidden="true" />
          </button>
        ) : null}
        <div className="min-w-0 flex-1 pt-2.5">
          <h2 id={titleId} ref={titleRef} tabIndex={titleRef ? -1 : undefined} className={`rounded-mark font-display ${headerSize === "large" ? "text-[21px]" : "text-[17px]"} font-medium text-black focus:outline-none focus-visible:outline focus-visible:outline-2 focus-visible:outline-[#2f5a49] dark:text-white ${titleIcon ? "flex items-center gap-2" : ""}`}>{titleIcon ? <span aria-hidden="true" className="flex shrink-0">{titleIcon}</span> : null}{title}</h2>
          {summary ? <p className={`mt-1 ${headerSize === "large" ? "text-[14px]" : "text-[13px]"} text-[#56635e] dark:text-white/70`}>{summary}</p> : null}
        </div>
        {expansion ? (
          <button type="button" onClick={expansion.onToggle} aria-label={expansion.expanded ? expansion.collapseLabel : expansion.expandLabel} aria-expanded={expansion.expanded} className={styles.expandButton}>
            {expansion.expanded ? <Minimize2 size={18} aria-hidden="true" /> : <Maximize2 size={18} aria-hidden="true" />}
          </button>
        ) : null}
        {dismissible && !hasBelow ? (
          <button
            type="button"
            onClick={onClose}
            aria-label={closeLabel}
            className="flex min-h-11 min-w-11 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        ) : null}
      </div>
      {back}
      <div className="argus-thin-scrollbar min-h-0 flex-1 overflow-y-auto">
        {children}
      </div>
      {footer ? (
        // A footer slot another component portals into takes no room while it is empty.
        <div className="shrink-0 border-t border-[#DCE0DA] px-5 py-3 has-[>[data-footer-slot]:empty]:hidden dark:border-white/10">
          {footer}
        </div>
      ) : null}
    </div>
  );
}

const SideDrawer = withViewportPortal(SideDrawerSurface);
