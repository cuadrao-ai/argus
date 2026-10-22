"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { discoverBusinessTransfers, respondToBusinessTransfer, type BusinessTransferDetails } from "@/lib/business-transfer-api";
import { businessLifecycleErrorKey } from "@/lib/business-lifecycle-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import { serverRequestReference } from "@/lib/failure-screen";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import BusinessTransferDialog, { useBusinessTransferCopy, type BusinessTransferView } from "./BusinessTransferDialog";
import type { BusinessCloseState } from "./BusinessCloseDialog";
import { secondaryButtonClass } from "./business-ui";

type Entry = { kind: "loading" | "unavailable" } | { kind: "failed"; reference: string | null } | { kind: "loaded"; transfer: BusinessTransferDetails };

export default function BusinessTransferEntry({ transferId }: { transferId: string }) {
  const { t } = useTranslation();
  const copy = useBusinessTransferCopy();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [command, setCommand] = useState<BusinessCloseState>({ kind: "idle" });
  const [refreshRequired, setRefreshRequired] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [dismissed, setDismissed] = useState(false);
  const busy = useRef(false);
  const dismiss = () => { setDismissed(true); const url = new URL(window.location.href); url.searchParams.delete("transfer"); window.history.replaceState(window.history.state, "", url); };
  useEffect(() => {
    const controller = new AbortController();
    const generation = browserAuthGeneration();
    if (!z.uuid().safeParse(transferId).success) { setEntry({ kind: "unavailable" }); return () => controller.abort(); }
    setEntry({ kind: "loading" });
    void discoverBusinessTransfers(controller.signal).then(transfers => {
      requireBrowserAuthGeneration(generation);
      if (controller.signal.aborted) return;
      const transfer = transfers.find(item => item.id === transferId);
      if (transfer) setChosenGrant(transfer.grant_id);
      setCommand({ kind: "idle" }); setRefreshRequired(false); busy.current = false;
      setEntry(transfer ? { kind: "loaded", transfer } : { kind: "unavailable" });
    }).catch(error => {
      if (controller.signal.aborted || browserAuthGeneration() !== generation) return;
      const status = typeof error === "object" && error !== null && "status" in error ? error.status : null;
      setEntry(status === 403 || status === 404 ? { kind: "unavailable" } : { kind: "failed", reference: serverRequestReference(error) });
    });
    return () => controller.abort();
  }, [transferId, attempt]);
  if (dismissed) return null;
  if (entry.kind !== "loaded") return <AdaptivePanel title={copy.title} closeLabel={copy.cancel} onClose={dismiss} width="md"><div className="space-y-3 p-5 text-[14px]">
    <p role={entry.kind === "loading" ? "status" : "alert"}>{entry.kind === "loading" ? t("common.loading") : t(entry.kind === "failed" ? "business.lifecycle.errors.transfer_load" : "business.lifecycle.errors.transfer_unavailable")}</p>
    {entry.kind === "failed" ? <>{entry.reference ? <ReferenceCode reference={entry.reference} /> : null}<button type="button" className={secondaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></> : null}
  </div></AdaptivePanel>;
  if (refreshRequired && command.kind === "error") return <AdaptivePanel title={copy.title} closeLabel={copy.cancel} onClose={dismiss} width="md"><div className="space-y-4 p-5"><p role="alert">{command.message}</p>{command.reference ? <ReferenceCode reference={command.reference} /> : null}<button type="button" className={secondaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("business.lifecycle.refresh")}</button></div></AdaptivePanel>;
  const transfer = entry.transfer;
  const execute = async (action: "accept" | "decline" | "withdraw") => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    setCommand({ kind: "submitting" });
    try {
      await respondToBusinessTransfer({ transferId, action });
      requireBrowserAuthGeneration(generation);
      window.location.assign(`/biz?transfer=${encodeURIComponent(transferId)}`);
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      setCommand({ kind: "error", message: t(businessLifecycleErrorKey(error, `${action}_uncertain`)), reference: serverRequestReference(error) });
      setRefreshRequired(true);
    }
  };
  let view: BusinessTransferView;
  if (transfer.status === "pending") view = transfer.role === "owner"
    ? { kind: "pending", expiresAt: transfer.expires_at, targetName: transfer.target_name, onWithdraw: () => { void execute("withdraw"); } }
    : { kind: "recipient", expiresAt: transfer.expires_at, ownerName: transfer.owner_name, onAccept: () => { void execute("accept"); }, onDecline: () => { void execute("decline"); } };
  else if (transfer.status === "declined" && transfer.role === "target") view = { kind: "declinedRecipient" };
  else if (transfer.status === "expired" || transfer.status === "declined") view = { kind: transfer.status, targetName: transfer.target_name };
  else view = { kind: transfer.status };
  return <BusinessTransferDialog businessName={transfer.business_name} copy={copy} view={view} state={command} onDismiss={dismiss} />;
}
