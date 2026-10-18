"use client";

import { useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { businessLifecycleHref, getClosedBusinessSpaces, getOwnedBusinessSpaces, reopenBusinessSpace, type BusinessLifecycleResult, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { randomId } from "@/lib/random-id";
import { businessOwnershipCopyEs } from "./BusinessOwnershipDeletionBlock";
import { secondaryButtonClass } from "./business-ui";

export default function BusinessLifecycleControls() {
  const { t } = useTranslation();
  const [listed, setListed] = useState<{ open: OwnedBusiness[]; closed: BusinessLifecycleResult[] } | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const keys = useRef(new Map<string, string>());
  const pending = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    void Promise.all([getOwnedBusinessSpaces(controller.signal), getClosedBusinessSpaces(controller.signal)]).then(([open, closed]) => { if (!controller.signal.aborted) setListed({ open, closed }); }).catch(() => undefined);
    return () => controller.abort();
  }, []);
  const reopen = async (spaceId: string) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(spaceId); setFailed(false);
    const generation = browserAuthGeneration();
    if (!keys.current.has(spaceId)) keys.current.set(spaceId, randomId());
    try {
      await reopenBusinessSpace({ spaceId, idempotencyKey: keys.current.get(spaceId)! });
      requireBrowserAuthGeneration(generation);
      window.location.assign("/biz");
    } catch { pending.current = false; setBusy(null); setFailed(true); }
  };
  if (!listed || !listed.open.length && !listed.closed.length) return null;
  return <div className="mt-6 space-y-4">
    {listed.open.map(business => <div key={business.space_id}><p className="break-words text-[15px] font-medium">{business.name}</p><div className="flex flex-wrap gap-3"><a className={secondaryButtonClass} href={businessLifecycleHref(business.space_id, "transfer")}>{businessOwnershipCopyEs.transfer}</a><a className={secondaryButtonClass} href={businessLifecycleHref(business.space_id, "close")}>{businessOwnershipCopyEs.close}</a></div></div>)}
    {listed.closed.map(business => <div key={business.space_id}><p className="break-words text-[15px] font-medium">{business.name}</p><button type="button" className={secondaryButtonClass} disabled={busy !== null} onClick={() => { void reopen(business.space_id); }}>{businessOwnershipCopyEs.reopen}</button></div>)}
    {failed ? <p role="alert" className="text-[14px]">{t("common.error_occurred")}</p> : null}
  </div>;
}
