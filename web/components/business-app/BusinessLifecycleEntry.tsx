"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { businessLifecycleErrorKey, closeBusinessSpace, getOwnedBusinessSpaces, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { discoverBusinessTransfers, requestBusinessTransfer } from "@/lib/business-transfer-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import { serverRequestReference } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import BusinessCloseDialog, { useBusinessCloseCopy, type BusinessCloseState } from "./BusinessCloseDialog";
import BusinessTransferDialog, { useBusinessTransferCopy } from "./BusinessTransferDialog";
import BusinessCloseExport, { type BusinessCloseExportJournal } from "./BusinessCloseExport";
import { secondaryButtonClass } from "./business-ui";

type Entry = { kind: "loading" | "unavailable" } | { kind: "failed"; reference: string | null } | { kind: "ready"; business: OwnedBusiness };

export default function BusinessLifecycleEntry({ spaceId, action }: { spaceId: string; action: "close" | "transfer" }) {
  const { t } = useTranslation();
  const closeCopy = useBusinessCloseCopy();
  const transferCopy = useBusinessTransferCopy();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<BusinessCloseState>({ kind: "idle" });
  const journal = useRef<{ input: string; key: string } | null>(null);
  const busy = useRef(false);
  const [exportJournal, setExportJournal] = useState<BusinessCloseExportJournal>({ nextWindow: 0, state: "idle" });
  const dismiss = () => window.location.assign("/biz");
  useEffect(() => {
    const controller = new AbortController();
    const generation = browserAuthGeneration();
    if (!z.uuid().safeParse(spaceId).success) { setEntry({ kind: "unavailable" }); return () => controller.abort(); }
    setEntry({ kind: "loading" });
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
    }).catch(error => {
      if (controller.signal.aborted || browserAuthGeneration() !== generation) return;
      setEntry(businessLifecycleErrorKey(error, "discovery").endsWith("business_unavailable") ? { kind: "unavailable" } : { kind: "failed", reference: serverRequestReference(error) });
    });
    return () => controller.abort();
  }, [spaceId, action, attempt]);
  if (entry.kind !== "ready") return <AdaptivePanel title={action === "close" ? closeCopy.title : transferCopy.title} closeLabel={closeCopy.cancel} onClose={dismiss} width="md"><div className="space-y-3 p-5 text-[14px]">
    <p role={entry.kind === "loading" ? "status" : "alert"}>{entry.kind === "loading" ? t("common.loading") : t(entry.kind === "failed" ? "business.lifecycle.errors.discovery" : "business.lifecycle.errors.business_unavailable")}</p>
    {entry.kind === "failed" ? <>{entry.reference ? <ReferenceCode reference={entry.reference} /> : null}<button type="button" className={secondaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></> : null}
  </div></AdaptivePanel>;
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
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      busy.current = false;
      setState({ kind: "error", message: t(businessLifecycleErrorKey(error, action === "close" ? "close_uncertain" : "request_uncertain")), reference: serverRequestReference(error), field: typeof error === "object" && error !== null && "code" in error && error.code === "business_name_mismatch" ? "confirmation" : undefined });
      if (typeof error === "object" && error !== null && "code" in error && error.code === "business_transfer_target_invalid") {
        void getOwnedBusinessSpaces().then(spaces => {
          requireBrowserAuthGeneration(generation);
          const refreshed = spaces.find(space => space.space_id === spaceId);
          setEntry(refreshed ? { kind: "ready", business: refreshed } : { kind: "unavailable" });
        }).catch(() => undefined);
      }
    }
  };
  if (action === "transfer") return <BusinessTransferDialog businessName={business.name} copy={transferCopy} view={{ kind: "request", members: business.members, onRequest: (grant, confirmation) => { void execute(confirmation, grant); } }} state={state} onDismiss={dismiss} />;
  return <BusinessCloseDialog businessName={business.name} preview={business} copy={closeCopy} state={state} onConfirm={confirmation => { void execute(confirmation); }} onCancel={dismiss} exportControl={<BusinessCloseExport key={business.space_id} business={business} label={closeCopy.download} journal={exportJournal} setJournal={setExportJournal} />} />;
}
