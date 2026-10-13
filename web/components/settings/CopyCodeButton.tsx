"use client";

import { Check, Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { copyText } from "@/lib/copy-text";

const SHOW_CHECK_MS = 1500;

/**
 * A small square button beside a code: press it, the full text lands on the
 * clipboard, the icon becomes a check for a moment and comes back. The name
 * stays "Copy code"; "Copied" is announced politely. A clipboard that refuses
 * never crashes the panel: the text stays selectable and the failure is
 * announced.
 */
export default function CopyCodeButton({ text }: { text: string }) {
  const { t } = useTranslation();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const copy = async () => {
    const copied = await copyText(text);
    setState(copied ? "copied" : "failed");
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), SHOW_CHECK_MS);
  };
  const copied = state === "copied";
  return (
    <>
      <button
        type="button"
        onClick={() => void copy()}
        aria-label={t("settings.whatsapp.copy_code", "Copy code")}
        data-testid="whatsapp-copy-code"
        data-state={state}
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-black/10 text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 dark:border-white/15 dark:text-white/70 dark:hover:bg-white/10 dark:focus-visible:ring-white/30"
      >
        <span className={`inline-flex transition-transform duration-200 ease-out ${copied ? "scale-110" : "scale-100"}`}>
          {copied ? <Check className="h-4 w-4 text-[var(--rui-color-teal)]" aria-hidden="true" /> : <Copy className="h-4 w-4" aria-hidden="true" />}
        </span>
      </button>
      <span role="status" aria-live="polite" className="sr-only">
        {copied ? t("settings.whatsapp.copied", "Copied") : state === "failed" ? t("settings.whatsapp.copy_failed", "Could not copy. Select the text to copy it.") : ""}
      </span>
    </>
  );
}
