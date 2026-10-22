"use client";

import { useEffect, useRef, useState } from "react";
import { X } from "lucide-react";
import type { ClosedGrantedSpace } from "@/lib/business-api";
import { useTranslation } from "react-i18next";
import { businessDeadlineParts, businessLifecycleErrorKey, businessLifecycleHref, getClosedBusinessSpaces, getOwnedBusinessSpaces, reopenBusinessSpace, type BusinessLifecycleResult, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { browserAuthGeneration, requireBrowserAuthGeneration } from "@/lib/browser-auth-generation";
import { randomId } from "@/lib/random-id";
import { serverRequestReference } from "@/lib/failure-screen";
import { resolveLanguage } from "@/lib/language-features";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { useBusinessOwnershipCopy } from "./BusinessOwnershipDeletionBlock";
import { primaryButtonClass, secondaryButtonClass, dangerButtonClass } from "./business-ui";
import { SURFACE_CARD } from "./foundation/surfaces";

type Listing = { kind: "loading" } | { kind: "hidden" } | { kind: "failed"; reference: string | null } | { kind: "ready"; open: OwnedBusiness[]; closed: BusinessLifecycleResult[] };

export default function BusinessLifecycleControls({ spaceId }: { spaceId?: string } = {}) {
  const { t, i18n } = useTranslation();
  const copy = useBusinessOwnershipCopy();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const [listed, setListed] = useState<Listing>({ kind: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [busy, setBusy] = useState<string | null>(null);
  const [failure, setFailure] = useState<{ spaceId: string; message: string; reference: string | null } | null>(null);
  const keys = useRef(new Map<string, string>());
  const pending = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    const generation = browserAuthGeneration();
    setListed({ kind: "loading" });
    void Promise.all([getOwnedBusinessSpaces(controller.signal), getClosedBusinessSpaces(controller.signal)]).then(([open, closed]) => {
      requireBrowserAuthGeneration(generation);
      if (!controller.signal.aborted) setListed({ kind: "ready", open, closed });
    }).catch(error => {
      if (controller.signal.aborted) return;
      const hidden = typeof error === "object" && error !== null && "code" in error && error.code === "business_unavailable";
      setListed(hidden ? { kind: "hidden" } : { kind: "failed", reference: serverRequestReference(error) });
    });
    return () => controller.abort();
  }, [attempt]);
  const reopen = async (business: BusinessLifecycleResult) => {
    if (pending.current) return;
    pending.current = true;
    setBusy(business.space_id); setFailure(null);
    const generation = browserAuthGeneration();
    if (!keys.current.has(business.space_id)) keys.current.set(business.space_id, randomId());
    try {
      await reopenBusinessSpace({ spaceId: business.space_id, idempotencyKey: keys.current.get(business.space_id)! });
      requireBrowserAuthGeneration(generation);
      window.location.assign("/biz");
    } catch (error) {
      if (browserAuthGeneration() !== generation) return;
      pending.current = false; setBusy(null);
      setFailure({ spaceId: business.space_id, message: t(businessLifecycleErrorKey(error, "reopen_uncertain")), reference: serverRequestReference(error) });
    }
  };
  if (listed.kind === "hidden") return null;
  if (listed.kind === "loading") return <p role="status" className="text-[14px]">{t("common.loading")}</p>;
  if (listed.kind === "failed") return <section className={SURFACE_CARD}><p role="alert">{t("business.lifecycle.errors.discovery")}</p>{listed.reference ? <ReferenceCode reference={listed.reference} /> : null}<button type="button" className={`${secondaryButtonClass} mt-3`} onClick={() => setAttempt(value => value + 1)}>{t("common.retry")}</button></section>;
  const open = listed.open.filter(business => !spaceId || business.space_id === spaceId);
  const closed = listed.closed.filter(business => !spaceId || business.space_id === spaceId);
  if (!open.length && !closed.length) return null;
  return <section data-testid="business-lifecycle-controls" className="space-y-5">
    {open.length ? <div className={SURFACE_CARD}>
      <h2 className="font-display text-[17px] font-medium">{t("business.lifecycle.owner_title")}</h2>
      {open.map(business => <div key={business.space_id} className="mt-5 space-y-3">
        {!spaceId ? <p className="break-words text-[15px] font-medium">{business.name}</p> : null}
        <div className="flex flex-wrap gap-3"><a className={secondaryButtonClass} href={businessLifecycleHref(business.space_id, "transfer")}>{copy.transfer}</a><a className={dangerButtonClass} href={businessLifecycleHref(business.space_id, "close")}>{copy.close}</a></div>
      </div>)}
    </div> : null}
    {closed.map(business => <article key={business.space_id} className={`${SURFACE_CARD} space-y-4`}>
      <h2 className="break-words font-display text-[24px] font-medium">{business.name}</h2>
      <p className="flex items-center gap-2 text-[14px] font-medium text-[#9e2f39] dark:text-[#ec9aa0]"><span aria-hidden="true" className="h-2 w-2 rounded-full bg-current" />{t("business.lifecycle.closed_status")}</p>
      <p>{business.reopen_until ? t("business.lifecycle.deadline", businessDeadlineParts(business.reopen_until, locale)) : null}</p>
      <p className="text-[14px] leading-relaxed">{t("business.lifecycle.purge_consequence")}</p>
      <p className="text-[14px] leading-relaxed">{t("business.lifecycle.closed_owner")}</p>
      <button type="button" className={primaryButtonClass} disabled={busy !== null} onClick={() => { void reopen(business); }}>{busy === business.space_id ? t("common.loading") : copy.reopen}</button>
      <p className="text-[14px] leading-relaxed text-[#56635e] dark:text-white/70">{t("business.lifecycle.reopen_access")}</p>
      {failure && failure.spaceId === business.space_id ? <div role="alert" className="space-y-2 text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]"><p>{failure.message}</p>{failure.reference ? <ReferenceCode reference={failure.reference} /> : null}</div> : null}
    </article>)}
  </section>;
}

export function BusinessClosedAccess({ businessName, onReturn, returnHome = false }: { businessName: string; onReturn: () => void; returnHome?: boolean }) {
  const { t } = useTranslation();
  return <section data-testid="business-member-closed" className="mx-auto flex min-h-[60dvh] max-w-xl flex-col justify-center gap-5 px-6 py-12 text-[#172b26] dark:text-white">
    <p className="flex items-center gap-2 text-[14px] font-medium text-[#9e2f39] dark:text-[#ec9aa0]"><span aria-hidden="true" className="h-2 w-2 rounded-full bg-current" />{t("business.lifecycle.closed_status")}</p>
    <p role="alert" className="text-[18px] leading-relaxed">{t("business.lifecycle.member_closed", { businessName })}</p>
    <button type="button" className={secondaryButtonClass} onClick={onReturn}>{t(returnHome ? "auth.screen.go_home" : "auth.screen.go_to_businesses")}</button>
  </section>;
}


export function BusinessClosedOwnerBanner({ businesses }: { businesses: ClosedGrantedSpace[] }) {
  const { t, i18n } = useTranslation();
  const [dismissed, setDismissed] = useState<string[]>([]);
  const held = businesses.filter(business => business.role === "owner" && !dismissed.includes(business.space_id));
  if (!held.length) return null;
  return <aside data-testid="business-closed-owner-banner" className="border-b border-[#dce0da] bg-[#f5f0e4] px-5 py-4 text-[#172b26] dark:border-white/10 dark:bg-[#20372f] dark:text-white">
    {held.map(business => <div key={business.space_id} className="mx-auto flex max-w-4xl items-start gap-3">
      <div className="min-w-0 flex-1 space-y-1">
        <p className="break-words text-[14px] font-medium">{business.name} · {t("business.lifecycle.closed_status")}</p>
        <p className="text-[13px]">{t("business.lifecycle.deadline", businessDeadlineParts(business.reopen_until, i18n.resolvedLanguage ?? resolveLanguage({})))}</p>
        <a className="inline-flex min-h-11 items-center text-[14px] underline" href={`/biz?lifecycle=manage&business=${encodeURIComponent(business.space_id)}`}>{t("business.lifecycle.reopen.action")}</a>
      </div>
      <button type="button" aria-label={t("common.close")} className="flex h-11 w-11 shrink-0 items-center justify-center rounded-item" onClick={() => setDismissed(values => [...values, business.space_id])}><X aria-hidden="true" className="h-5 w-5" /></button>
    </div>)}
  </aside>;
}
