"use client";

import { Copy } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { copyText } from "@/lib/copy-text";

export const SHOW_CHECK_MS = 1500;

/**
 * A small square button beside a code: press it, the full text lands on the
 * clipboard, the icon becomes a check for a moment and comes back. The name
 * stays "Copy code"; "Copied" is announced politely, again on every press. A
 * clipboard that refuses never crashes the panel: the text stays selectable
 * and the failure is announced. Motion is skipped when the person asks for
 * reduced motion.
 */
export default function CopyCodeButton({ text, showCheckMs = SHOW_CHECK_MS }: { text: string; showCheckMs?: number }) {
  const { t } = useTranslation();
  const [state, setState] = useState<"idle" | "copied" | "failed">("idle");
  // Counts presses so the live region is a new node each time and re-announces.
  const [presses, setPresses] = useState(0);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current) clearTimeout(timer.current);
  }, []);
  const copy = async () => {
    const copied = await copyText(text);
    setState(copied ? "copied" : "failed");
    setPresses((count) => count + 1);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setState("idle"), showCheckMs);
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
        className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-lg border border-black/10 text-black/70 transition-colors hover:bg-black/5 focus-visible:outline-none focus-visible:ring-[0.125rem] focus-visible:ring-black/25 motion-reduce:transition-none dark:border-white/15 dark:text-white/70 dark:hover:bg-white/10 dark:focus-visible:ring-white/30"
      >
        <Copy aria-hidden="true" data-icon="copy" className={`h-4 w-4 transition-[opacity,scale] duration-150 ease-out motion-reduce:transition-none ${copied ? "scale-75 opacity-0" : "scale-100 opacity-100"}`}/>
        <svg aria-hidden="true" data-icon={copied ? "check" : undefined} viewBox="0 0 24 24" className="absolute h-4 w-4 text-[var(--cuadrao-green)]">
          <path d="m5 12 4 4 10-10" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" pathLength="1" strokeDasharray="1" strokeDashoffset={copied ? 0 : 1}
            className={copied ? "transition-[stroke-dashoffset] duration-[250ms] ease-out motion-reduce:transition-none" : "opacity-0"} />
        </svg>
      </button>
      <span key={presses} role="status" aria-live="polite" data-presses={presses} className="sr-only">
        {copied ? t("settings.whatsapp.copied", "Copied") : state === "failed" ? t("settings.whatsapp.copy_failed", "Could not copy. Select the text to copy it.") : ""}
      </span>
    </>
  );
}
