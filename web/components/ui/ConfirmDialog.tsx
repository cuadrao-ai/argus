"use client";

import { withViewportPortal } from "@/components/ui/withViewportPortal";

import { useId, useRef, useCallback, useEffect, type ReactNode } from "react";
import { useModalSurface } from "@/components/layout/useModalSurface";
import { KeyboardShortcutKeycap } from "@/components/keyboard/KeyboardShortcutKeycap";
import { CONFIRM_ACTION, FOCUS_RING } from "@/components/business-app/foundation/presentation";

type ConfirmDialogProps = {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel: string;
  cancelLabel: string;
  isBusy?: boolean;
  showKeyboardHints?: boolean;
  /** `danger` for a delete; `primary` for a full stop that removes nothing, such as closing a month. */
  tone?: "danger" | "primary";
  /** The confirm failed: says so inside the alert, and the confirm button tries again. */
  error?: ReactNode;
  children?: ReactNode;
  details?: ReactNode;
  testId?: string;
  /** An alternate decision is independent of dismissal. Focus starts on the primary action. */
  secondaryAction?: { label: string; onClick: () => void } | null;
  leadingAction?: ReactNode;
  onCancel: () => void;
  onConfirm: () => void;
};

type ConfirmDialogKeyboardAction = "cancel" | "confirm" | "none";

export function confirmDialogKeyboardAction({
  key,
  isBusy,
  showKeyboardHints,
  targetIsButton,
}: {
  key: string;
  isBusy: boolean;
  showKeyboardHints: boolean;
  targetIsButton: boolean;
}): ConfirmDialogKeyboardAction {
  if (key === "Escape") return "cancel";
  if (
    key === "Enter" &&
    showKeyboardHints &&
    !isBusy &&
    !targetIsButton
  ) {
    return "confirm";
  }
  return "none";
}

function ConfirmDialogSurface({
  isOpen,
  title,
  description,
  confirmLabel,
  cancelLabel,
  isBusy = false,
  showKeyboardHints = false,
  tone = "danger",
  error = null,
  children,
  details,
  testId,
  secondaryAction,
  leadingAction,
  onCancel,
  onConfirm,
}: ConfirmDialogProps) {
  const overlayId = useId();
  const panelRef = useRef<HTMLDivElement>(null);
  const initialFocusRef = useRef<HTMLButtonElement>(null);
  const confirmLock = useRef(false);
  const sawBusy = useRef(false);
  useEffect(() => {
    if (!isOpen) {
      confirmLock.current = false;
      sawBusy.current = false;
      return;
    }
    if (isBusy) sawBusy.current = true;
    if (!isBusy && (sawBusy.current || error)) {
      sawBusy.current = false;
      confirmLock.current = false;
    }
  }, [error, isBusy, isOpen]);
  const confirmOnce = useCallback(() => {
    if (confirmLock.current || isBusy) return;
    confirmLock.current = true;
    onConfirm();
  }, [isBusy, onConfirm]);
  // A confirmation is the topmost surface wherever it opens, so it registers
  // for Escape, for focus, and for system back: without the last one, hardware
  // back closed the drawer underneath and took the confirmation with it.
  const handleKeyDown = useCallback(
    (event: KeyboardEvent) => {
      const action = confirmDialogKeyboardAction({
        key: event.key,
        isBusy,
        showKeyboardHints,
        targetIsButton:
          event.target instanceof Element &&
          Boolean(event.target.closest("button")),
      });
      if (action === "cancel") {
        event.preventDefault();
        event.stopPropagation();
        onCancel();
        return;
      }
      if (action === "confirm") {
        event.preventDefault();
        event.stopPropagation();
        confirmOnce();
      }
    },
    [confirmOnce, isBusy, onCancel, showKeyboardHints],
  );

  useModalSurface({
    isOpen,
    overlayId,
    containerRef: panelRef,
    initialFocusRef,
    onDismiss: onCancel,
    // `onCancel` refuses while the delete is in flight, and refusing inside the
    // dismissal is too late: the entry is claimed by then, so the dialog stayed
    // open owning an id it had spent and no later press could close it.
    canDismiss: () => !isBusy,
    // Confirm owns Enter as well as Escape, so it takes the whole keydown. The
    // registry still only offers it while this dialog is the topmost layer.
    onKeyDown: handleKeyDown,
  });

  if (!isOpen) return null;
  const secondary = secondaryAction === undefined ? { label: cancelLabel, onClick: onCancel } : secondaryAction;

  return (
    <div className="fixed inset-0 z-[130] flex items-center justify-center bg-black/40 p-4 dark:bg-black/60">
      <button
        tabIndex={-1}
        type="button"
        className="absolute inset-0"
        aria-label={cancelLabel}
        onClick={onCancel}
      />
      <div
        ref={panelRef}
        role="alertdialog"
        data-testid={testId}
        aria-modal="true"
        aria-labelledby="argus-confirm-title"
        aria-describedby="argus-confirm-description"
        className={`relative w-full rounded-surface border border-black/10 bg-white p-5 dark:border-white/10 dark:bg-[#1f2225] ${details ? "max-h-[calc(100dvh-2rem)] max-w-lg overflow-y-auto" : "max-w-sm"}`}
      >
        <h2
          id="argus-confirm-title"
          className="font-display text-[17px] font-medium tracking-tight text-black dark:text-white"
        >
          {title}
        </h2>
        {children}
        <p
          id="argus-confirm-description"
          className="mt-2 text-[13px] leading-relaxed text-black/55 dark:text-white/55"
        >
          {description}
        </p>
        {details}
        {error ? (
          <p role="alert" data-testid="confirm-dialog-error" className="mt-3 text-[13px] leading-relaxed text-[#9e2f39] dark:text-[#ec9aa0]">
            {error}
          </p>
        ) : null}
        <div className="mt-5 flex flex-wrap justify-end gap-2">
          {leadingAction ? <div className="mr-auto">{leadingAction}</div> : null}
          {secondary && <button
            ref={secondaryAction === undefined ? initialFocusRef : undefined}
            type="button"
            onClick={secondary.onClick}
            disabled={isBusy}
            className={`min-h-11 rounded-full border border-black/10 px-4 text-[16px] font-medium text-black hover:bg-black/5 disabled:opacity-50 ${FOCUS_RING} dark:border-[var(--segment-thumb-border)] dark:text-white dark:hover:bg-white/5`}
          >
            <span className="inline-flex items-center gap-2">
              {secondary.label}
              {showKeyboardHints && (
                <KeyboardShortcutKeycap className="!h-6 !min-w-0 !rounded-mark !px-2">
                  Esc
                </KeyboardShortcutKeycap>
              )}
            </span>
          </button>}
          <button
            ref={secondaryAction !== undefined ? initialFocusRef : undefined}
            type="button"
            onClick={confirmOnce}
            disabled={isBusy}
            data-testid="confirm-dialog-confirm"
            aria-busy={isBusy || undefined}
            style={tone === "danger" ? { backgroundColor: CONFIRM_ACTION } : undefined}
            className={`min-h-11 rounded-full px-4 text-[16px] font-medium ${tone === "danger" ? "text-white" : "bg-[var(--cuadrao-green)] text-[var(--cuadrao-cream)]"} hover:opacity-90 disabled:opacity-50 ${FOCUS_RING}`}
          >
            <span className="inline-flex items-center gap-2">
              {confirmLabel}
              {showKeyboardHints && (
                <KeyboardShortcutKeycap className="!h-6 !min-w-0 !rounded-mark !bg-white/15 !px-2 !text-white">
                  ↵
                </KeyboardShortcutKeycap>
              )}
            </span>
          </button>
        </div>
      </div>
    </div>
  );
}

export const ConfirmDialog = withViewportPortal(ConfirmDialogSurface);
