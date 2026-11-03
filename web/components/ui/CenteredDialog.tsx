"use client";

import { useId, useRef, useState, type ReactNode, type RefObject } from "react";
import { X } from "lucide-react";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { useResponsiveLayout } from "@/components/layout/useResponsiveLayout";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { withViewportPortal } from "@/components/ui/withViewportPortal";
import styles from "./centered-dialog.module.css";

/**
 * One short task, such as sending a comment: centered over a scrim on
 * desktop, the shared sheet below the desktop stop. The title and close sit
 * at the top, the body scrolls, and the footer holds the one next step.
 */

type CenteredDialogProps = {
  title: string;
  closeLabel: string;
  onClose: () => void;
  /** Where focus lands on open; the close control otherwise. */
  initialFocusRef?: RefObject<HTMLElement | null>;
  returnFocusRef?: RefObject<HTMLElement | null>;
  footer?: ReactNode;
  testId?: string;
  children: ReactNode;
};

function DesktopSurface({ title, closeLabel, onClose, initialFocusRef, returnFocusRef, footer, testId, children }: CenteredDialogProps) {
  const overlayId = useId();
  const titleId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  // Read while rendering, before a field's autoFocus moves focus during commit,
  // so closing finds the control that opened the dialog rather than that field.
  const [opener] = useState(() => (document.activeElement instanceof HTMLElement ? document.activeElement : null));
  const openerRef = useRef(opener);
  useModalSurface({ isOpen: true, overlayId, containerRef: panelRef, onDismiss: onClose, initialFocusRef: initialFocusRef ?? closeRef, returnFocusRef: returnFocusRef ?? openerRef });

  return (
    <div className={`fixed inset-0 z-[70] flex items-center justify-center bg-black/40 p-8 dark:bg-black/60 ${styles.scrim}`}>
      <button type="button" tabIndex={-1} aria-label={closeLabel} className="absolute inset-0 cursor-default" onClick={onClose} />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        data-testid={testId}
        className={`relative flex max-h-[min(720px,calc(100dvh-64px))] w-[min(520px,100%)] flex-col overflow-hidden rounded-surface border border-[#DCE0DA] bg-white text-[#172b26] dark:border-white/10 dark:bg-[#1b1d20] dark:text-white ${styles.dialog}`}
      >
        <header className="flex shrink-0 items-start justify-between gap-3 pl-6 pr-3 pt-3">
          <h2 id={titleId} className="pt-2 font-display text-[21px] font-medium">{title}</h2>
          <button
            ref={closeRef}
            type="button"
            aria-label={closeLabel}
            onClick={onClose}
            className="flex h-11 w-11 shrink-0 items-center justify-center rounded-full text-black/60 transition-colors hover:bg-black/5 hover:text-black focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)] dark:text-white/60 dark:hover:bg-white/10 dark:hover:text-white"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>
        <div className="argus-thin-scrollbar flex min-h-0 flex-1 flex-col overflow-y-auto">{children}</div>
        {footer ? <div className="shrink-0 border-t border-[#DCE0DA] px-6 py-3 dark:border-white/10">{footer}</div> : null}
      </div>
    </div>
  );
}

const DesktopDialog = withViewportPortal(DesktopSurface);

export default function CenteredDialog(props: CenteredDialogProps) {
  const { isBelowDesktop } = useResponsiveLayout();
  if (!isBelowDesktop) return <DesktopDialog {...props} />;
  const { title, closeLabel, onClose, initialFocusRef, returnFocusRef, footer, children } = props;
  return (
    <AdaptivePanel title={title} closeLabel={closeLabel} onClose={onClose} initialFocusRef={initialFocusRef} returnFocusRef={returnFocusRef} footer={footer} width="lg">
      {children}
    </AdaptivePanel>
  );
}
