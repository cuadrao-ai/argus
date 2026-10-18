"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { discoverBusinessTransfers, respondToBusinessTransfer, type BusinessTransferDetails } from "@/lib/business-transfer-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import BusinessTransferDialog, { businessTransferCopyEs, type BusinessTransferView } from "./BusinessTransferDialog";
import type { BusinessCloseState } from "./BusinessCloseDialog";

type Entry = { kind: "loading" } | { kind: "unavailable" } | { kind: "loaded"; transfer: BusinessTransferDetails };

export default function BusinessTransferEntry({ transferId }: { transferId: string }) {
  const { t } = useTranslation();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [command, setCommand] = useState<BusinessCloseState>({ kind: "idle" });
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
      setEntry(transfer ? { kind: "loaded", transfer } : { kind: "unavailable" });
    }).catch(() => { if (!controller.signal.aborted) setEntry({ kind: "unavailable" }); });
    return () => controller.abort();
  }, [transferId]);
  if (dismissed) return null;
  if (entry.kind !== "loaded") return <AdaptivePanel title={businessTransferCopyEs.title} closeLabel={businessTransferCopyEs.cancel} onClose={dismiss} width="md"><p role="status" className="p-5 text-[14px]">{entry.kind === "loading" ? t("common.loading") : t("common.error_occurred")}</p></AdaptivePanel>;
  const transfer = entry.transfer;
  const act = async (action: "accept" | "decline" | "withdraw") => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    setCommand({ kind: "submitting" });
    try {
      await respondToBusinessTransfer({ transferId, action });
      requireBrowserAuthGeneration(generation);
      window.location.assign(`/biz?transfer=${encodeURIComponent(transferId)}`);
    } catch { busy.current = false; setCommand({ kind: "error", message: t("common.error_occurred") }); }
  };
  let view: BusinessTransferView;
  if (transfer.status === "pending") view = transfer.role === "owner"
    ? { kind: "pending", targetName: transfer.target_name, onWithdraw: () => { void act("withdraw"); } }
    : { kind: "recipient", ownerName: transfer.owner_name, onAccept: () => { void act("accept"); }, onDecline: () => { void act("decline"); } };
  else if (transfer.status === "declined" && transfer.role === "target") view = { kind: "declinedRecipient" };
  else if (transfer.status === "expired" || transfer.status === "declined") view = { kind: transfer.status, targetName: transfer.target_name };
  else view = { kind: transfer.status };
  return <BusinessTransferDialog businessName={transfer.business_name} copy={businessTransferCopyEs} view={view} state={command} onDismiss={dismiss} />;
}
