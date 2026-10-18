"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { closeBusinessSpace, getOwnedBusinessSpaces, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { discoverBusinessTransfers, requestBusinessTransfer } from "@/lib/business-transfer-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import { randomId } from "@/lib/random-id";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import BusinessCloseDialog, { businessCloseCopyEs, type BusinessCloseState } from "./BusinessCloseDialog";
import BusinessTransferDialog, { businessTransferCopyEs } from "./BusinessTransferDialog";
import { ReceiptPeriodExport } from "./ReceiptDossierReview";

type Entry = { kind: "loading" | "unavailable" } | { kind: "ready"; business: OwnedBusiness };

export default function BusinessLifecycleEntry({ spaceId, action }: { spaceId: string; action: "close" | "transfer" }) {
  const { t } = useTranslation();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [state, setState] = useState<BusinessCloseState>({ kind: "idle" });
  const [dismissed, setDismissed] = useState(false);
  const journal = useRef<{ input: string; key: string } | null>(null);
  const busy = useRef(false);
  const dismiss = () => { setDismissed(true); const url = new URL(window.location.href); url.searchParams.delete("lifecycle"); url.searchParams.delete("business"); window.history.replaceState(window.history.state, "", url); };
  useEffect(() => {
    const controller = new AbortController();
    const generation = browserAuthGeneration();
    if (!z.uuid().safeParse(spaceId).success) { setEntry({ kind: "unavailable" }); return () => controller.abort(); }
    void getOwnedBusinessSpaces(controller.signal).then(async spaces => {
      requireBrowserAuthGeneration(generation);
      const business = spaces.find(space => space.space_id === spaceId);
      if (!business || controller.signal.aborted) { if (!controller.signal.aborted) setEntry({ kind: "unavailable" }); return; }
      setChosenGrant(business.grant_id);
      if (action === "transfer") {
        const pending = (await discoverBusinessTransfers(controller.signal)).find(item => item.space_id === spaceId && item.status === "pending");
        requireBrowserAuthGeneration(generation);
        if (controller.signal.aborted) return;
        if (pending) { window.location.assign(`/biz?transfer=${encodeURIComponent(pending.id)}`); return; }
      }
      setEntry({ kind: "ready", business });
    }).catch(() => { if (!controller.signal.aborted) setEntry({ kind: "unavailable" }); });
    return () => controller.abort();
  }, [spaceId, action]);
  if (dismissed) return null;
  if (entry.kind !== "ready") return <AdaptivePanel title={action === "close" ? businessCloseCopyEs.title : businessTransferCopyEs.title} closeLabel={businessCloseCopyEs.cancel} onClose={dismiss} width="md"><p role="status" className="p-5 text-[14px]">{entry.kind === "loading" ? t("common.loading") : t("common.error_occurred")}</p></AdaptivePanel>;
  const { business } = entry;
  const execute = async (confirmation: string, targetGrantId?: string) => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    const input = JSON.stringify([spaceId, action, confirmation, targetGrantId]);
    if (journal.current?.input !== input) journal.current = { input, key: randomId() };
    setState({ kind: "submitting" });
    try {
      const idempotencyKey = journal.current.key;
      const result = action === "close"
        ? await closeBusinessSpace({ spaceId, confirmation, idempotencyKey })
        : await requestBusinessTransfer({ spaceId, confirmation, targetGrantId: targetGrantId!, idempotencyKey });
      requireBrowserAuthGeneration(generation);
      window.location.assign("id" in result ? `/biz?transfer=${encodeURIComponent(result.id)}` : "/biz?lifecycle=manage");
    } catch { busy.current = false; setState({ kind: "error", message: t("common.error_occurred") }); }
  };
  if (action === "transfer") return <BusinessTransferDialog businessName={business.name} copy={businessTransferCopyEs} view={{ kind: "request", members: business.members.map(member => ({ grantId: member.grant_id, name: member.name })), onRequest: (grant, confirmation) => { void execute(confirmation, grant); } }} state={state} onDismiss={dismiss} />;
  return <BusinessCloseDialog businessName={business.name} copy={businessCloseCopyEs} state={state} onConfirm={confirmation => { void execute(confirmation); }} onCancel={dismiss} exportControl={<ReceiptPeriodExport scope={{ grantId: business.grant_id, name: business.name, capabilities: ["read", "prepare", "approve"] }} start="" end="" available />} />;
}
