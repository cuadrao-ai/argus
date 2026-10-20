"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { Check, Copy } from "lucide-react";
import { useTranslation } from "react-i18next";

/** How long the check stays before the copy icon returns. */
export const COPIED_HOLD_MS = 2000;

type CopyState = "idle" | "copied" | "failed";

/** The legacy copy command, for origins where the async clipboard is missing or refused. */
function copyWithCommand(value: string): boolean {
  const field = document.createElement("textarea");
  field.value = value;
  field.setAttribute("readonly", "");
  field.style.position = "fixed";
  field.style.opacity = "0";
  document.body.appendChild(field);
  field.select();
  let copied = false;
  try {
    copied = document.execCommand("copy");
  } catch {
    copied = false;
  }
  field.remove();
  return copied;
}

/** Copies the raw value, never rendered text; the async clipboard first, the copy command when it is refused. */
export async function copyText(value: string): Promise<boolean> {
  try {
    if (!navigator.clipboard?.writeText) throw new Error("clipboard_unavailable");
    await navigator.clipboard.writeText(value);
    return true;
  } catch {
    return copyWithCommand(value);
  }
}

/**
 * One copy control: the icon flips to a check the moment the copy lands,
 * holds it for two seconds and fades back, so every copy gives a signal. A
 * live region says it out loud; a failure is said too, never silent.
 */
export function CopyButton({ value, label, copiedLabel, failedLabel, onFailed, className, testId, children }: {
  value: string;
  /** The button's name, also its aria-label when it shows only the icon. */
  label: string;
  copiedLabel: string;
  failedLabel: string;
  onFailed?: () => void;
  className: string;
  testId?: string;
  /** Visible text beside the icon; absent for an icon-only button. */
  children?: ReactNode;
}) {
  const [state, setState] = useState<CopyState>("idle");
  const timer = useRef<number | null>(null);
  useEffect(() => () => {
    if (timer.current !== null) window.clearTimeout(timer.current);
  }, []);
  const copy = async () => {
    const copied = await copyText(value);
    if (timer.current !== null) window.clearTimeout(timer.current);
    const next: CopyState = copied ? "copied" : "failed";
    if (!copied) onFailed?.();
    const show = () => {
      setState(next);
      timer.current = window.setTimeout(() => setState("idle"), COPIED_HOLD_MS);
    };
    // A repeat copy empties the live region first, so the same words are read again.
    if (state === next) {
      setState("idle");
      timer.current = window.setTimeout(show, 60);
    } else show();
  };
  const done = state === "copied";
  return (
    <>
      <button type="button" aria-label={children ? undefined : label} data-testid={testId} data-copy-state={state} className={className} onClick={() => void copy()}>
        <span className="relative inline-flex h-4 w-4 shrink-0 items-center justify-center" aria-hidden="true">
          <Copy className={`absolute h-4 w-4 transition-opacity duration-200 motion-reduce:transition-none ${done ? "opacity-0" : "opacity-100"}`} />
          <Check className={`absolute h-4 w-4 transition-opacity duration-200 motion-reduce:transition-none ${done ? "opacity-100" : "opacity-0"}`} strokeWidth={2.5} />
        </span>
        {children}
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {state === "copied" ? copiedLabel : state === "failed" ? failedLabel : ""}
      </span>
    </>
  );
}

/** An email address that wraps after the @ instead of inside a word. Copy the raw string, not this. */
export function WrappingAddress({ address }: { address: string }) {
  const at = address.indexOf("@");
  if (at < 0) return <>{address}</>;
  return <>{address.slice(0, at + 1)}<wbr />{address.slice(at + 1)}</>;
}

export function useCopyLabels(address: string) {
  const { t } = useTranslation();
  return {
    copiedLabel: t("business.email.copied", "Address copied."),
    failedLabel: t("business.overview.copy_forward_failed", { address, defaultValue: "Could not copy. Your forwarding address is {{address}}" }),
  };
}
