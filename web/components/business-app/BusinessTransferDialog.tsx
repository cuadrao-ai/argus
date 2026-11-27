"use client";

import { useId, useRef, useState, type ReactNode } from "react";
import { Loader2 } from "lucide-react";
import { useTranslation } from "react-i18next";
import { FormField } from "@/components/ui/FormField";
import { Avatar } from "@/components/ui/Avatar";
import { ReferenceCode } from "@/components/status/ReferenceCode";
import { businessDeadlineParts, type OwnedBusiness } from "@/lib/business-lifecycle-api";
import { resolveLanguage } from "@/lib/language-features";
import { personName } from "@/lib/person-name";
import { BusinessCloseShell, NamedCopy, type BusinessCloseState } from "./BusinessCloseDialog";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";

/** Every state a transfer can show. Each one is the same dialog. */
export type BusinessTransferView =
  | { kind: "loading" }
  | { kind: "unavailable"; of: "business" | "transfer" }
  | { kind: "failed"; of: "business" | "transfer"; reference: string | null; onRetry: () => void }
  | { kind: "request"; businessName: string; members: OwnedBusiness["members"]; onRequest: (grantId: string, confirmation: string) => void }
  | { kind: "pending"; expiresAt?: string | null; targetName: string; onWithdraw: () => void }
  | { kind: "recipient"; businessName: string; expiresAt?: string | null; ownerName: string; onAccept: () => void; onDecline: () => void }
  | { kind: "declined"; businessName: string; targetName: string }
  | { kind: "expired"; targetName: string }
  | { kind: "expiredLink" | "accepted" | "cancelled" | "declinedRecipient" };

const NAME_SLOT = "\u0000";
const mutedTextClass = "text-[#56635e] dark:text-white/70";
const bodyTextClass = "text-black/75 dark:text-white/75";
const alertTextClass = "text-[#9e2f39] dark:text-[#ec9aa0]";

/** The accept question with the Business name in bold; the sentence itself carries no markup. One element, so a sheet's title row cannot space its words apart. */
function AcceptTitle({ businessName }: { businessName: string }) {
  const { t } = useTranslation();
  const [before, after = ""] = t("business.lifecycle.transfer.accept_title", { businessName: NAME_SLOT }).split(NAME_SLOT);
  return <span>{before}<strong className="font-bold">{businessName}</strong>{after}</span>;
}

function Spinner() {
  return <Loader2 className="h-4 w-4 animate-spin motion-reduce:animate-none" aria-hidden="true" />;
}

/**
 * Transferring a Business is one dialog, the one Cerrar negocio uses: the owner
 * picks a member and types the name, the recipient answers one question, and
 * every notice, wait and failure shows in that same dialog.
 */
export default function BusinessTransferDialog({ view, state, onDismiss, onRefresh }: {
  view: BusinessTransferView;
  state: BusinessCloseState;
  onDismiss: () => void;
  /** Set when an answer's outcome is unknown: the only next step reads the server again. */
  onRefresh?: () => void;
}) {
  const { t, i18n } = useTranslation();
  const locale = i18n.resolvedLanguage ?? resolveLanguage({});
  const nameId = useId();
  const memberId = useId();
  const helpId = useId();
  const memberRef = useRef<HTMLInputElement>(null);
  const [confirmation, setConfirmation] = useState("");
  const [grantId, setGrantId] = useState("");
  const [pressed, setPressed] = useState<"accept" | "decline" | null>(null);
  const submitting = state.kind === "submitting";
  const failed = state.kind === "error";
  const members = view.kind === "request" ? view.members : [];
  const firstEligible = members.findIndex((member) => member.eligible);
  const canRequest = view.kind === "request" && members.some((member) => member.grant_id === grantId && member.eligible) && view.businessName.length > 0 && confirmation === view.businessName && !submitting;
  const request = () => { if (view.kind === "request" && canRequest) view.onRequest(grantId, confirmation); };
  const expiry = (view.kind === "pending" || view.kind === "recipient") && view.expiresAt
    ? <p className={mutedTextClass}>{t("business_access.pending_until", { date: Object.values(businessDeadlineParts(view.expiresAt, locale)).join(", ") })}</p>
    : null;
  const notice = (role: "status" | "alert", message: string) => <p role={role} className={role === "alert" ? alertTextClass : bodyTextClass}>{message}</p>;

  let footer: ReactNode = null;
  if (onRefresh && failed) footer = <button type="button" className={primaryButtonClass} onClick={onRefresh}>{t("business.lifecycle.refresh")}</button>;
  else if (view.kind === "request" && firstEligible >= 0) footer = <>
    <button type="button" className={secondaryButtonClass} disabled={submitting} onClick={onDismiss}>{t("common.cancel")}</button>
    <button type="button" className={primaryButtonClass} disabled={!canRequest} aria-busy={submitting || undefined} onClick={request}>{submitting ? <Spinner /> : null}{t("business.lifecycle.transfer.request")}</button>
  </>;
  else if (view.kind === "pending") footer = <button type="button" className={secondaryButtonClass} disabled={submitting} aria-busy={submitting || undefined} onClick={view.onWithdraw}>{submitting ? <Spinner /> : null}{t("business.lifecycle.transfer.withdraw")}</button>;
  else if (view.kind === "recipient") footer = <>
    <button type="button" className={secondaryButtonClass} disabled={submitting} aria-busy={(submitting && pressed === "decline") || undefined} onClick={() => { setPressed("decline"); view.onDecline(); }}>{submitting && pressed === "decline" ? <Spinner /> : null}{t("business.lifecycle.transfer.decline")}</button>
    <button type="button" className={primaryButtonClass} disabled={submitting} aria-busy={(submitting && pressed === "accept") || undefined} onClick={() => { setPressed("accept"); view.onAccept(); }}>{submitting && pressed === "accept" ? <Spinner /> : null}{t("business.lifecycle.transfer.accept")}</button>
  </>;
  else if (view.kind === "failed") footer = <button type="button" className={secondaryButtonClass} onClick={view.onRetry}>{t("common.retry")}</button>;

  return (
    <BusinessCloseShell
      title={view.kind === "recipient" ? <AcceptTitle businessName={view.businessName} /> : t("business.lifecycle.transfer.title")}
      closeLabel={t("common.close")}
      onClose={onDismiss}
      locked={submitting}
      initialFocusRef={view.kind === "request" && firstEligible >= 0 ? memberRef : undefined}
      footer={footer ? <div className="flex flex-wrap justify-end gap-2">{footer}</div> : undefined}
    >
      <div data-testid="business-transfer" data-view={view.kind} className="text-[14px] leading-relaxed" aria-busy={submitting || undefined}>
        {view.kind === "loading" ? <p role="status" className={`flex min-h-16 items-center gap-2.5 ${mutedTextClass}`}><Loader2 className="h-5 w-5 animate-spin motion-reduce:animate-none" aria-hidden="true" />{t("common.loading")}</p> : null}
        {view.kind === "unavailable" ? notice("alert", t(view.of === "business" ? "business.lifecycle.errors.business_unavailable" : "business.lifecycle.errors.transfer_unavailable")) : null}
        {view.kind === "failed" ? <div className={`space-y-2 ${alertTextClass}`}>{notice("alert", t(view.of === "business" ? "business.lifecycle.errors.discovery" : "business.lifecycle.errors.transfer_load"))}{view.reference ? <ReferenceCode reference={view.reference} /> : null}</div> : null}
        {view.kind === "expiredLink" ? notice("alert", t("business.lifecycle.errors.transfer_expired")) : null}
        {view.kind === "declined" ? notice("status", t("business.lifecycle.transfer.declined", { targetName: view.targetName, businessName: view.businessName })) : null}
        {view.kind === "expired" ? notice("status", t("business.lifecycle.transfer.expired", { targetName: view.targetName })) : null}
        {view.kind === "accepted" ? notice("status", t("business.lifecycle.transfer.accepted")) : null}
        {view.kind === "cancelled" ? notice("status", t("business.lifecycle.transfer.cancelled")) : null}
        {view.kind === "declinedRecipient" ? notice("status", t("business.lifecycle.transfer.declined_recipient")) : null}
        {view.kind === "request" && members.length === 0 ? notice("status", t("business.lifecycle.transfer.empty")) : null}
        {view.kind === "request" && members.length > 0 ? <>
          <fieldset aria-describedby={helpId}>
            <legend className="mb-2.5 block font-medium">{t("business.lifecycle.transfer.member")}</legend>
            <div className="space-y-2" role="radiogroup" aria-label={t("business.lifecycle.transfer.member")}>
              {members.map((member, index) => {
                const name = personName(t, { display_name: member.name, email: member.email, shown_as: member.shown_as });
                const reasonId = `${memberId}-${member.grant_id}`;
                return (
                  <label key={member.grant_id} className={`flex min-h-[60px] items-center gap-3 rounded-item border border-black/15 px-3 py-2.5 dark:border-white/20 ${member.eligible ? "cursor-pointer hover:bg-[#172b26]/[0.06] has-[:checked]:border-[var(--cuadrao-green)] has-[:checked]:shadow-[0_0_0_1px_var(--cuadrao-green)] dark:hover:bg-white/[0.06]" : "opacity-55"}`}>
                    <input ref={index === firstEligible ? memberRef : undefined} type="radio" name={memberId} value={member.grant_id} checked={grantId === member.grant_id && member.eligible} disabled={submitting || !member.eligible} onChange={() => setGrantId(member.grant_id)} aria-describedby={!member.eligible ? reasonId : undefined} className="h-[18px] w-[18px] shrink-0 rounded-full accent-[var(--cuadrao-green)] focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[var(--cuadrao-green)]" />
                    <Avatar name={name} size={32} />
                    <span className="min-w-0">
                      <span className="block break-words text-[15px] font-medium">{name}</span>
                      {member.eligible ? null : <span id={reasonId} className={`block ${mutedTextClass}`}>{t(`business.lifecycle.transfer.ineligible.${member.reason}`)}</span>}
                    </span>
                  </label>
                );
              })}
            </div>
            <p id={helpId} className={`mt-3 ${mutedTextClass}`}>{t(firstEligible >= 0 ? "business.lifecycle.transfer.help" : "business.lifecycle.transfer.none_eligible")}</p>
          </fieldset>
          {firstEligible >= 0 ? <form className="mt-5" onSubmit={(event) => { event.preventDefault(); request(); }}>
            <FormField id={nameId} label={<NamedCopy i18nKey="business.lifecycle.close.confirmation" businessName={view.businessName} />} value={confirmation} onChange={(event) => setConfirmation(event.target.value)} disabled={submitting} error={failed && state.field ? state.message : undefined} autoComplete="off" autoCapitalize="off" spellCheck={false} />
          </form> : null}
        </> : null}
        {view.kind === "pending" ? <div className="space-y-1.5"><p>{t("business.lifecycle.transfer.pending", { targetName: view.targetName })}</p>{expiry}</div> : null}
        {view.kind === "recipient" ? <div className="space-y-2.5"><p className={bodyTextClass}>{t("business.lifecycle.transfer.accept_body", { ownerName: view.ownerName })}</p>{expiry}</div> : null}
        {failed ? <div role="alert" className={`mt-4 space-y-2 ${alertTextClass}`}>{!state.field ? <p>{state.message}</p> : null}{state.reference ? <ReferenceCode reference={state.reference} /> : null}</div> : null}
      </div>
    </BusinessCloseShell>
  );
}
