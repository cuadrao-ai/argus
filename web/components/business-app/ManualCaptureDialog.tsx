"use client";

import { useEffect, useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import type { BusinessCaptureInput } from "@/lib/business-api";
import type { BusinessDossier } from "@/lib/business-dossier";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "./BusinessWorkspace";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

export function validCaptureText(text: string): boolean {
  return Boolean(text.trim()) && [...text].length <= 20000 && !text.includes("\0");
}

export function captureOutcomeUnknown(status: number | undefined, code: string | undefined): boolean {
  return status === 409 && (code === "business_action_unsettled" || code === "outcome_unknown");
}

type Phase = "idle" | "saving" | "uncertain" | "refused";

export default function ManualCaptureDialog({ isOpen, target, revision, onClose, onSaved, onPending, onRetained, onUnavailable }: {
  isOpen: boolean;
  target?: BusinessCaptureInput["draft"];
  /** The facts revision the note is added to, as the record's history lists it; `target.version` is what the API checks. */
  revision?: number;
  onClose: () => void;
  onSaved: (dossier: BusinessDossier) => void;
  onPending?: (pending: boolean) => void;
  onRetained?: (retained: boolean) => void;
  onUnavailable?: () => void;
}) {
  const { t } = useTranslation();
  const textId = useId();
  const { source } = useBusiness();
  const [text, setText] = useState("");
  const [accessDenied, setAccessDenied] = useState(false);
  const [phase, setPhase] = useState<Phase>("idle");
  const [submittedTarget, setSubmittedTarget] = useState<BusinessCaptureInput["draft"]>();
  const [problem, setProblem] = useState<string | null>(null);
  const command = useRef<{ input: BusinessCaptureInput; key: string } | null>(null);
  const inFlight = useRef(false);
  const active = useRef(true);
  useEffect(() => { active.current = true; return () => { active.current = false; }; }, []);

  const save = async () => {
    if (inFlight.current || phase === "refused" || !validCaptureText(text)) return;
    command.current ??= { input: { text, ...(target ? { draft: { ...target } } : {}) }, key: randomId() };
    const submitted = command.current;
    setSubmittedTarget(submitted.input.draft);
    inFlight.current = true;
    setPhase("saving");
    setProblem(null);
    onPending?.(true);
    try {
      const saved = await source.captureNote(submitted.input, submitted.key);
      if (!active.current) return;
      command.current = null;
      setSubmittedTarget(undefined);
      setText("");
      onRetained?.(false);
      setPhase("idle");
      onPending?.(false);
      onSaved(saved);
    } catch (error) {
      if (!active.current) return;
      const { status, code } = error as { status?: number; code?: string };
      if (status && status >= 400 && status < 500 && !captureOutcomeUnknown(status, code)) {
        setPhase("refused");
        onPending?.(false);
        const unavailable = status === 401 || status === 403 || status === 404 || code === "permission_denied";
        setProblem(unavailable ? t("business.capture.unavailable", "Your current access does not allow saving this note. Your text is retained.") : code === "stale_version" ? t("business.capture.stale", "This record changed. Close this note, check the current revision, then reopen it. Your text is retained.") : t("business.capture.refused", "The note could not be saved. Your text is retained; review the request before trying again."));
        setAccessDenied(unavailable);
        if (unavailable) onUnavailable?.();
      } else {
        setPhase("uncertain");
        setProblem(t("business.capture.uncertain", "We could not confirm whether the note was saved. Your original request is retained. Retry only this same request to check its outcome."));
      }
    } finally { inFlight.current = false; }
  };

  if (!isOpen) return null;
  const saving = phase === "saving";
  const displayedTarget = submittedTarget ?? target;
  return <AdaptivePanel title={t(target ? "business.capture.append" : "business.capture.write", target ? "Add a note to this record" : "Save a note")} closeLabel={t("common.close", "Close")} onClose={() => { if (!saving) onClose(); }} width="md">
    <form onSubmit={(event) => { event.preventDefault(); void save(); }} className="space-y-4 p-5">
      <p className="text-[14px] leading-relaxed text-black/65 dark:text-white/65">{t("business.capture.help", "Save your original words for review. This creates no assistant reply and records no money movement.")}</p>
      {displayedTarget && revision !== undefined ? <p className="text-[13px] text-black/60 dark:text-white/60">{t("business.capture.target_revision", "Record revision {{version}}", { version: revision })}</p> : null}
      <label htmlFor={textId} className="block text-[13px] font-medium text-black/65 dark:text-white/65">{t("business.capture.text", "Original note")}</label><textarea id={textId} value={text} onChange={(event) => { setText(event.target.value); onRetained?.(event.target.value.length > 0); }} readOnly={phase !== "idle"} required autoFocus rows={7} className="mt-2 block w-full rounded-[16px] border border-black/15 bg-transparent p-3 text-[16px] font-normal leading-relaxed text-black outline-none focus-visible:ring-2 focus-visible:ring-black/20 dark:border-white/20 dark:text-white" />
      {problem ? <p role="alert" className="text-[14px] leading-relaxed text-black/75 dark:text-white/75">{problem}</p> : null}
      <div className="flex flex-wrap gap-3">
        <button type="button" disabled={saving} className={secondaryButtonClass} onClick={onClose}>{t("common.close", "Close")}</button>
        {phase === "refused" && !accessDenied ? <button type="button" className={secondaryButtonClass} onClick={() => { command.current = null; setSubmittedTarget(undefined); setPhase("idle"); setProblem(null); }}>{t("business.capture.edit_request", "Edit request")}</button> : null}
        <button type="submit" disabled={saving || phase === "refused" || !validCaptureText(text)} className={primaryButtonClass}>{t(saving ? "business.capture.saving" : phase === "uncertain" ? "business.capture.retry" : "business.capture.save", saving ? "Saving…" : phase === "uncertain" ? "Retry the same note" : "Save note")}</button>
      </div>
    </form>
  </AdaptivePanel>;
}
