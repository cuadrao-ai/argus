"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { getChosenGrant } from "@/lib/business-grant";
import type { BusinessDossier } from "@/lib/business-dossier";
import { appendBusinessReportSupportingFile, downloadBusinessReportAttachment, setBusinessReportCurrentNote, setBusinessReportSupportingFileLink } from "@/lib/business-reports-api";
import { randomId } from "@/lib/random-id";
import { useBusiness } from "../BusinessWorkspace";
import { dismissToast, showToast } from "../foundation/toasts";
import { useShownRecord } from "../useShownRecord";

type Edit = { kind: "note"; note: string } | { kind: "append"; file: File } | { kind: "unlink" | "restore"; sourceId: string };

/** Mutations return the full dossier, including the next version and the offers for Undo and Historial. */
export function useDossierAnnotations(dossier: BusinessDossier | null, blocked: boolean, onChanged: (next: BusinessDossier) => void, onReadFailure: (error: unknown) => void, onUndoFailure: (error: unknown) => void) {
  const { chosen, userId, source, reload } = useBusiness();
  const { t } = useTranslation();
  const grantId = getChosenGrant();
  const businessId = dossier?.space_id;
  const scope = useMemo(() => userId && businessId && chosen?.space_id === businessId && source.mode === "live"
    ? { userId, businessId, grantId } : null, [businessId, chosen?.space_id, grantId, source.mode, userId]);
  const readFile = useCallback(async (receiptId: string, signal: AbortSignal) => {
    if (!scope) throw new Error("Record unavailable");
    return downloadBusinessReportAttachment(scope, receiptId, signal);
  }, [scope]);
  const identity = JSON.stringify([userId, grantId, dossier?.draft_id]);
  const shown = useShownRecord(identity);
  const [busy, setBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const pending = useRef<{ version: number; value: string | File; kind: Edit["kind"]; key: string } | null>(null);
  const undo = useRef<{ toast: number; version: number; sourceId: string } | null>(null);
  useEffect(() => {
    const offer = undo.current;
    if (offer && (blocked || offer.version !== dossier?.version || !dossier.supporting_files?.some(file => file.source_id === offer.sourceId && file.restore_available))) {
      dismissToast(offer.toast);
      undo.current = null;
    }
  }, [blocked, dossier]);
  useEffect(() => () => {
    request.current?.abort();
    if (undo.current) dismissToast(undo.current.toast);
  }, [identity]);

  const send = async (edit: Edit, record: BusinessDossier) => {
    if (!scope || blocked || request.current || !shown(identity)) throw new Error("Record unavailable");
    const value = edit.kind === "note" ? edit.note : edit.kind === "append" ? edit.file : edit.sourceId;
    const last = pending.current;
    const key = last && last.version === record.version && last.value === value && last.kind === edit.kind ? last.key : randomId();
    pending.current = { version: record.version, value, kind: edit.kind, key };
    const command = { draftId: record.draft_id, expectedVersion: record.version, key };
    const abort = new AbortController();
    request.current = abort;
    setBusy(true);
    try {
      const answer = edit.kind === "note" ? await setBusinessReportCurrentNote(scope, { ...command, note: edit.note }, abort.signal)
        : edit.kind === "append" ? await appendBusinessReportSupportingFile(scope, { ...command, file: edit.file }, abort.signal)
        : await setBusinessReportSupportingFileLink(scope, { ...command, sourceId: edit.sourceId }, edit.kind, abort.signal);
      if (!shown(identity)) return;
      pending.current = null;
      onChanged(answer.dossier);
      reload();
      if (edit.kind === "unlink") {
        const next = answer.dossier;
        const offered = next.supporting_files?.some(file => file.source_id === edit.sourceId && file.restore_available);
        const toast = showToast({ kind: "success", text: t("business.dossier.supporting.unlinked_toast"),
          action: offered ? { label: t("business.dossier.supporting.undo"), run: () => {
            void send({ kind: "restore", sourceId: edit.sourceId }, next).catch(error => { if (shown(identity)) onUndoFailure(error); });
          } } : undefined });
        undo.current = offered ? { toast, version: next.version, sourceId: edit.sourceId } : null;
      }
    } catch (error) {
      const status = (error as { status?: number })?.status;
      if (shown(identity) && (status === 401 || status === 403)) reload();
      if (shown(identity) && (status === 401 || status === 403 || status === 404 || status === 409 || status === 422)) {
        try {
          const next = await source.dossier(record.draft_id);
          if (shown(identity)) onChanged(next);
        } catch (readError) { if (shown(identity)) onReadFailure(readError); }
      }
      throw error;
    } finally {
      request.current = null;
      if (shown(identity)) setBusy(false);
    }
  };
  return {
    busy,
    readFile: scope && chosen?.permissions?.includes("download") ? readFile : undefined,
    onSaveNote: scope && dossier?.note_edit_available ? (note: string) => send({ kind: "note", note }, dossier) : undefined,
    onAppend: scope && dossier?.supporting_append_available && !dossier.supporting_limit_reached ? (file: File) => send({ kind: "append", file }, dossier) : undefined,
    onUnlink: scope && dossier ? (sourceId: string) => send({ kind: "unlink", sourceId }, dossier) : undefined,
    onRestore: scope && dossier ? (sourceId: string) => send({ kind: "restore", sourceId }, dossier) : undefined,
  };
}
