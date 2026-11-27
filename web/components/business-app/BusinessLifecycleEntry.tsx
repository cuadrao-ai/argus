"use client";

import { useEffect, useRef, useState, type ComponentProps } from "react";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { businessLifecycleErrorKey, closeBusinessSpace, getOwnedBusinessSpaces, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { setChosenGrant } from "@/lib/business-grant";
import { serverRequestReference } from "@/lib/failure-screen";
import { randomId } from "@/lib/random-id";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import BusinessCloseDialog, { BusinessCloseShell, useBusinessCloseCopy, type BusinessCloseState } from "./BusinessCloseDialog";
import { useBusinessCloseDownloads } from "./useBusinessCloseDownloads";
import { ToastViewport } from "./foundation/ToastViewport";
import { secondaryButtonClass } from "./business-ui";
import { formatBusinessName } from "./business-format";

type Entry = { kind: "loading" | "unavailable" } | { kind: "failed"; reference: string | null } | { kind: "ready"; business: OwnedBusiness };

/** Cerrar negocio, opened from the Dueño card's link. */
export default function BusinessLifecycleEntry({ spaceId }: { spaceId: string }) {
  const { t } = useTranslation();
  const closeCopy = useBusinessCloseCopy();
  const [entry, setEntry] = useState<Entry>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [state, setState] = useState<BusinessCloseState>({ kind: "idle" });
  const journal = useRef<{ input: string; key: string } | null>(null);
  const busy = useRef(false);
  const dismiss = () => window.location.assign("/biz");
  useEffect(() => {
    const controller = new AbortController();
    const generation = browserAuthGeneration();
    if (!z.uuid().safeParse(spaceId).success) { setEntry({ kind: "unavailable" }); return () => controller.abort(); }
    setEntry({ kind: "loading" });
    void getOwnedBusinessSpaces(controller.signal).then(spaces => {
      requireBrowserAuthGeneration(generation);
      const business = spaces.find(space => space.space_id === spaceId);
      if (!business || controller.signal.aborted) { if (!controller.signal.aborted) setEntry({ kind: "unavailable" }); return; }
      setChosenGrant(business.grant_id);
      setEntry({ kind: "ready", business });
    }).catch(error => {
      if (controller.signal.aborted || browserAuthGeneration() !== generation) return;
      setEntry(businessLifecycleErrorKey(error, "discovery").endsWith("business_unavailable") ? { kind: "unavailable" } : { kind: "failed", reference: serverRequestReference(error) });
    });
    return () => controller.abort();
  }, [spaceId, attempt]);
  if (entry.kind !== "ready") {
    const status = <div className="space-y-3 text-[14px]">
      <p role={entry.kind === "loading" ? "status" : "alert"}>{entry.kind === "loading" ? t("common.loading") : t(entry.kind === "failed" ? "business.lifecycle.errors.discovery" : "business.lifecycle.errors.business_unavailable")}</p>
      {entry.kind === "failed" ? <>{entry.reference ? <ReferenceCode reference={entry.reference} /> : null}<button type="button" className={secondaryButtonClass} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></> : null}
    </div>;
    return <BusinessCloseShell title={closeCopy.title} closeLabel={closeCopy.cancel} onClose={dismiss}>{status}</BusinessCloseShell>;
  }
  const { business } = entry;
  const execute = async (confirmation: string) => {
    if (busy.current) return;
    busy.current = true;
    const generation = browserAuthGeneration();
    const input = JSON.stringify([spaceId, confirmation]);
    if (journal.current?.input !== input) journal.current = { input, key: randomId() };
    setState({ kind: "submitting" });
    try {
      await closeBusinessSpace({ spaceId, confirmation, idempotencyKey: journal.current.key });
      requireBrowserAuthGeneration(generation);
      window.location.assign("/biz?lifecycle=manage");
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      busy.current = false;
      setState({ kind: "error", message: t(businessLifecycleErrorKey(error, "close_uncertain")), reference: serverRequestReference(error), field: typeof error === "object" && error !== null && "code" in error && error.code === "business_name_mismatch" ? "confirmation" : undefined });
    }
  };
  return <BusinessCloseFlow key={business.space_id} business={business} businessName={formatBusinessName(business.name, t("business.overview.title", "My business"))} copy={closeCopy} state={state} onConfirm={confirmation => { void execute(confirmation); }} onCancel={dismiss} />;
}

/** The close dialog with this Business's own handover downloads. */
function BusinessCloseFlow({ business, ...dialog }: { business: OwnedBusiness } & Omit<ComponentProps<typeof BusinessCloseDialog>, "preview" | "downloads">) {
  const downloads = useBusinessCloseDownloads(business);
  // This entry draws without the workspace, so it brings the toast's one place with it.
  return <><BusinessCloseDialog {...dialog} preview={business} downloads={downloads} /><ToastViewport /></>;
}
