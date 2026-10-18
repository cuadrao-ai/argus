"use client";

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PLAIN_TOAST_MS, UNDO_TOAST_MS } from "./presentation";

export type ToastKind = "confirm" | "undo" | "error";

export function ToastNotice({
  text,
  kind,
  onUndo,
  onClose,
}: {
  text: string;
  kind: ToastKind;
  onUndo?: () => void;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [paused, setPaused] = useState(false);
  const duration = kind === "undo" ? UNDO_TOAST_MS : PLAIN_TOAST_MS;
  useEffect(() => {
    if (paused) return;
    const timer = window.setTimeout(onClose, duration);
    return () => window.clearTimeout(timer);
  }, [duration, onClose, paused, text]);
  return (
    <div
      role="status"
      aria-live={kind === "error" ? "assertive" : "polite"}
      data-testid="undo-toast"
      data-toast-kind={kind}
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocus={() => setPaused(true)}
      onBlur={() => setPaused(false)}
      className="fixed inset-x-4 bottom-24 z-[60] mx-auto flex max-w-md items-center justify-between gap-3 rounded-[12px] bg-[#172b26] px-4 py-3 text-[16px] text-[#fffefa]"
    >
      <span className="min-w-0 break-words">{text}</span>
      {onUndo ? (
        <button
          type="button"
          onClick={onUndo}
          className="inline-flex min-h-11 shrink-0 items-center rounded-full px-3 text-[16px] font-medium underline-offset-2 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#fffefa]"
        >
          {t("business.marks.undo", "Deshacer")}
        </button>
      ) : null}
    </div>
  );
}

export function ToastQueue({
  items,
  onDismiss,
}: {
  items: readonly { text: string; kind: ToastKind; onUndo?: () => void }[];
  onDismiss: () => void;
}) {
  const current = items[0];
  if (!current) return null;
  return <ToastNotice text={current.text} kind={current.kind} onUndo={current.onUndo} onClose={onDismiss} />;
}
