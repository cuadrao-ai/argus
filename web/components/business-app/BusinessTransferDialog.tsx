"use client";

import { useId, useRef, useState } from "react";
import spanish from "@/public/locales/es-419/common.json";
import { FormField } from "@/components/ui/FormField";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { businessDeadlineParts } from "@/lib/business-lifecycle-api";
import { resolveLanguage } from "@/lib/language-features";
import { useTranslation } from "react-i18next";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { Avatar } from "@/components/ui/Avatar";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import type { BusinessCloseState } from "./BusinessCloseDialog";

export const businessTransferCopyEs = {
  title: spanish.business.lifecycle.transfer.title,
  member: spanish.business.lifecycle.transfer.member,
  help: spanish.business.lifecycle.transfer.help,
  request: spanish.business.lifecycle.transfer.request,
  pending: spanish.business.lifecycle.transfer.pending,
  withdraw: spanish.business.lifecycle.transfer.withdraw,
  recipient: spanish.business.lifecycle.transfer.recipient,
  accept: spanish.business.lifecycle.transfer.accept,
  decline: spanish.business.lifecycle.transfer.decline,
  declined: spanish.business.lifecycle.transfer.declined,
  expired: spanish.business.lifecycle.transfer.expired,
  empty: spanish.business.lifecycle.transfer.empty,
  accepted: spanish.business.lifecycle.transfer.accepted,
  cancelled: spanish.business.lifecycle.transfer.cancelled,
  declinedRecipient: spanish.business.lifecycle.transfer.declined_recipient,
  confirmation: spanish.business.lifecycle.name_confirmation,
  cancel: spanish.common.cancel,
};

export function useBusinessTransferCopy() {
  const { t } = useTranslation();
  return {
    title: t("business.lifecycle.transfer.title", businessTransferCopyEs.title),
    member: t("business.lifecycle.transfer.member", businessTransferCopyEs.member),
    help: t("business.lifecycle.transfer.help", businessTransferCopyEs.help),
    request: t("business.lifecycle.transfer.request", businessTransferCopyEs.request),
    pending: t("business.lifecycle.transfer.pending", businessTransferCopyEs.pending),
    withdraw: t("business.lifecycle.transfer.withdraw", businessTransferCopyEs.withdraw),
    recipient: t("business.lifecycle.transfer.recipient", businessTransferCopyEs.recipient),
    accept: t("business.lifecycle.transfer.accept", businessTransferCopyEs.accept),
    decline: t("business.lifecycle.transfer.decline", businessTransferCopyEs.decline),
    declined: t("business.lifecycle.transfer.declined", businessTransferCopyEs.declined),
    expired: t("business.lifecycle.transfer.expired", businessTransferCopyEs.expired),
    empty: t("business.lifecycle.transfer.empty", businessTransferCopyEs.empty),
    accepted: t("business.lifecycle.transfer.accepted", businessTransferCopyEs.accepted),
    cancelled: t("business.lifecycle.transfer.cancelled", businessTransferCopyEs.cancelled),
    declinedRecipient: t("business.lifecycle.transfer.declined_recipient", businessTransferCopyEs.declinedRecipient),
    confirmation: t("business.lifecycle.name_confirmation", businessTransferCopyEs.confirmation),
    cancel: t("common.cancel", businessTransferCopyEs.cancel),
  };
}

type TransferCopy = { [Key in keyof typeof businessTransferCopyEs]: string };
export type BusinessTransferView =
  | { kind: "request"; members: OwnedBusiness["members"]; onRequest: (grantId: string, confirmation: string) => void }
  | { kind: "pending"; expiresAt?: string | null; targetName: string; onWithdraw: () => void }
  | { kind: "recipient"; expiresAt?: string | null; ownerName: string; onAccept: () => void; onDecline: () => void }
  | { kind: "declined"; targetName: string }
  | { kind: "expired"; targetName: string }
  | { kind: "accepted" | "cancelled" | "declinedRecipient" };

function text(template: string, values: Record<string, string>): string {
  return template.replace(/\{\{([^}]+)\}\}/g, (token: string, key: string) => values[key] ?? token);
}

export default function BusinessTransferDialog({ businessName, copy, view, state, onDismiss }: {
  businessName: string;
  copy: TransferCopy;
  view: BusinessTransferView;
  state: BusinessCloseState;
  onDismiss: () => void;
}) {
  const { t, i18n } = useTranslation();
  const [confirming, setConfirming] = useState(false);
  const nameId = useId();
  const memberId = useId();
  const helpId = useId();
  const memberRef = useRef<HTMLInputElement>(null);
  const [confirmation, setConfirmation] = useState("");
  const [grantId, setGrantId] = useState("");
  const submitting = state.kind === "submitting";
  const dismiss = () => { if (!submitting) onDismiss(); };
  const firstEligible = view.kind === "request" ? view.members.findIndex(member => member.eligible) : -1;
  const canRequest = view.kind === "request" && view.members.some((member) => member.grant_id === grantId && member.eligible) && businessName.length > 0 && confirmation === businessName && !submitting;

  if (confirming && view.kind === "recipient") return <ConfirmDialog isOpen title={t("business.lifecycle.transfer.accept_title", { businessName })} description={t("business.lifecycle.transfer.accept_body", { ownerName: view.ownerName })} confirmLabel={copy.accept} cancelLabel={copy.cancel} tone="primary" isBusy={submitting} error={state.kind === "error" ? state.message : null} onCancel={() => { if (!submitting) setConfirming(false); }} onConfirm={view.onAccept} />;
  return <AdaptivePanel title={copy.title} closeLabel={copy.cancel} onClose={dismiss} width="md" initialFocusRef={view.kind === "request" ? memberRef : undefined}>
    <div className="space-y-5 p-5" aria-busy={submitting}>
      {view.kind === "request" ? <form className="space-y-5" onSubmit={(event) => { event.preventDefault(); if (canRequest) view.onRequest(grantId, confirmation); }}>
        {view.members.length === 0 ? <p className="text-[14px] leading-relaxed">{copy.empty}</p> : null}
        <fieldset aria-describedby={helpId}>
          <legend className="block text-[14px]">{copy.member}</legend>
          <div className="mt-2 space-y-2" role="radiogroup" aria-label={copy.member}>
            {view.members.map((member, index) => <label key={member.grant_id} className="flex min-h-14 items-center gap-3 rounded-item border border-black/15 px-3 py-2 dark:border-white/20">
              <input ref={index === firstEligible ? memberRef : undefined} type="radio" name={memberId} value={member.grant_id} checked={grantId === member.grant_id && member.eligible} disabled={submitting || !member.eligible} onChange={() => setGrantId(member.grant_id)} aria-describedby={!member.eligible ? `${memberId}-${member.grant_id}` : undefined} />
              <Avatar name={member.name} size={32} />
              <span className="min-w-0 text-[14px]">
                <span className="block break-words">{member.name}</span>
                {member.eligible ? <span className="block text-black/60 dark:text-white/60">{t("business.switcher.role_editor")}</span> : <span id={`${memberId}-${member.grant_id}`} className="block text-black/60 dark:text-white/60">{t(`business.lifecycle.transfer.ineligible.${member.reason}`)}</span>}
              </span>
            </label>)}
          </div>
          <p id={helpId} className="mt-2 text-[14px] leading-relaxed text-black/75 dark:text-white/75">{copy.help}</p>
          {view.members.length && !view.members.some(member => member.eligible) ? <p className="mt-2 text-[14px]">{t("business.lifecycle.transfer.none_eligible")}</p> : null}
        </fieldset>
        <div>
          <p className="mb-2 break-words text-[16px] font-semibold">{businessName}</p>
          <FormField id={nameId} label={copy.confirmation} value={confirmation} disabled={submitting} onChange={event => setConfirmation(event.target.value)} error={state.kind === "error" && state.field ? state.message : undefined} autoComplete="off" autoCapitalize="off" spellCheck={false} />
        </div>
        {!canRequest && !submitting ? <p className="text-[14px] text-black/60 dark:text-white/60">{t("business.lifecycle.transfer.choose_reason")}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="submit" className={primaryButtonClass} disabled={!canRequest}>{copy.request}</button>
        </div>
      </form> : null}
      {(view.kind === "pending" || view.kind === "recipient") && view.expiresAt ? <p className="text-[14px] text-black/60 dark:text-white/60">{t("business_access.pending_until", { date: Object.values(businessDeadlineParts(view.expiresAt, i18n.resolvedLanguage ?? resolveLanguage({}))).join(", ") })}</p> : null}
      {view.kind === "pending" ? <>
        <p className="text-[14px] leading-relaxed">{text(copy.pending, { targetName: view.targetName })}</p>
        <div className="flex justify-end"><button type="button" className={secondaryButtonClass} disabled={submitting} onClick={view.onWithdraw}>{copy.withdraw}</button></div>
      </> : null}
      {view.kind === "recipient" ? <>
        <p className="text-[14px] leading-relaxed">{text(copy.recipient, { ownerName: view.ownerName, businessName })}</p>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={secondaryButtonClass} disabled={submitting} onClick={view.onDecline}>{copy.decline}</button>
          <button type="button" className={primaryButtonClass} disabled={submitting} onClick={() => setConfirming(true)}>{copy.accept}</button>
        </div>
      </> : null}
      {view.kind === "declined" ? <p className="text-[14px] leading-relaxed">{text(copy.declined, { targetName: view.targetName, businessName })}</p> : null}
      {view.kind === "expired" ? <p className="text-[14px] leading-relaxed">{text(copy.expired, { targetName: view.targetName })}</p> : null}
      {view.kind === "accepted" || view.kind === "cancelled" || view.kind === "declinedRecipient" ? <p className="text-[14px] leading-relaxed">{copy[view.kind]}</p> : null}
      {state.kind === "error" ? <div role="alert" className="space-y-2 text-[14px] leading-relaxed">{!state.field ? <p>{state.message}</p> : null}{state.reference ? <ReferenceCode reference={state.reference} /> : null}</div> : null}
    </div>
  </AdaptivePanel>;
}
