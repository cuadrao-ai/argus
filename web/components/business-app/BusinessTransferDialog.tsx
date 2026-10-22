"use client";

import { useId, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import type { OwnedBusiness } from "@/lib/business-lifecycle-api";
import { Avatar } from "@/components/ui/Avatar";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { primaryButtonClass, secondaryButtonClass } from "./business-ui";
import type { BusinessCloseState } from "./BusinessCloseDialog";

export const businessTransferCopyEs = {
  title: "Transferir este negocio",
  member: "Nuevo dueño",
  help: "Elige un miembro del negocio. Será dueño cuando acepte.",
  confirmation: "Escribe el nombre del negocio para confirmar.",
  request: "Solicitar transferencia",
  cancel: "Cancelar",
  pending: "Esperando que {Nombre} acepte.",
  withdraw: "Retirar solicitud",
  recipient: "{Dueño} quiere transferirte {Negocio}. Si aceptas, serás su dueño y {Dueño} podrá seguir editando.",
  accept: "Aceptar transferencia",
  decline: "Rechazar",
  declined: "{Nombre} rechazó la transferencia. {Negocio} sigue siendo tuyo.",
  expired: "La solicitud a {Nombre} venció.",
  empty: "Para transferir el negocio, primero invita a un miembro.",
  accepted: "Transferencia completada",
  cancelled: "Transferencia retirada",
  declinedRecipient: "Transferencia rechazada",
};

type TransferCopy = { [Key in keyof typeof businessTransferCopyEs]: string };
export type BusinessTransferView =
  | { kind: "request"; members: OwnedBusiness["members"]; onRequest: (grantId: string, confirmation: string) => void }
  | { kind: "pending"; targetName: string; onWithdraw: () => void }
  | { kind: "recipient"; ownerName: string; onAccept: () => void; onDecline: () => void }
  | { kind: "declined"; targetName: string }
  | { kind: "expired"; targetName: string }
  | { kind: "accepted" | "cancelled" | "declinedRecipient" };

function text(template: string, values: Record<string, string>): string {
  return template.replace(/\{([^}]+)\}/g, (token: string, key: string) => values[key] ?? token);
}

export default function BusinessTransferDialog({ businessName, copy, view, state, onDismiss }: {
  businessName: string;
  copy: TransferCopy;
  view: BusinessTransferView;
  state: BusinessCloseState;
  onDismiss: () => void;
}) {
  const { t } = useTranslation();
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
                {member.eligible ? <span className="block text-black/60 dark:text-white/60">{t("business.switcher.role_editor", { defaultValue: "Editar" })}</span> : <span id={`${memberId}-${member.grant_id}`} className="block text-black/60 dark:text-white/60">{t(`business.lifecycle.transfer.ineligible.${member.reason}`, { defaultValue: {
                  account_unavailable: "Esta cuenta no puede recibir el negocio.",
                  not_editor: "No tiene acceso para editar.",
                  email_unconfirmed: "Falta confirmar su correo.",
                  owns_open_business: "Ya es dueño de otro negocio abierto.",
                }[member.reason] })}</span>}
              </span>
            </label>)}
          </div>
          <p id={helpId} className="mt-2 text-[14px] leading-relaxed text-black/75 dark:text-white/75">{copy.help}</p>
          {view.members.length && !view.members.some(member => member.eligible) ? <p className="mt-2 text-[14px]">{t("business.lifecycle.transfer.none_eligible", { defaultValue: "Ningún miembro puede recibir el negocio ahora. Revisa el motivo junto a cada persona." })}</p> : null}
        </fieldset>
        <div>
          <p className="mb-2 break-words text-[16px] font-semibold">{businessName}</p>
          <label htmlFor={nameId} className="block text-[14px]">{copy.confirmation}</label>
          <input id={nameId} value={confirmation} disabled={submitting} onChange={(event) => setConfirmation(event.target.value)} autoComplete="off" autoCapitalize="off" spellCheck={false} className="mt-2 min-h-11 w-full rounded-item border border-black/15 bg-transparent px-3 text-[16px] dark:border-white/20" />
        </div>
        {!canRequest && !submitting ? <p className="text-[14px] text-black/60 dark:text-white/60">{t("business.lifecycle.transfer.choose_reason", { defaultValue: "Elige a una persona y escribe el nombre del negocio." })}</p> : null}
        <div className="flex flex-wrap justify-end gap-2">
          <button type="submit" className={primaryButtonClass} disabled={!canRequest}>{copy.request}</button>
        </div>
      </form> : null}
      {view.kind === "pending" ? <>
        <p className="text-[14px] leading-relaxed">{text(copy.pending, { Nombre: view.targetName })}</p>
        <div className="flex justify-end"><button type="button" className={secondaryButtonClass} disabled={submitting} onClick={view.onWithdraw}>{copy.withdraw}</button></div>
      </> : null}
      {view.kind === "recipient" ? <>
        <p className="text-[14px] leading-relaxed">{text(copy.recipient, { Dueño: view.ownerName, Negocio: businessName })}</p>
        <div className="flex flex-wrap justify-end gap-2">
          <button type="button" className={secondaryButtonClass} disabled={submitting} onClick={view.onDecline}>{copy.decline}</button>
          <button type="button" className={primaryButtonClass} disabled={submitting} onClick={view.onAccept}>{copy.accept}</button>
        </div>
      </> : null}
      {view.kind === "declined" ? <p className="text-[14px] leading-relaxed">{text(copy.declined, { Nombre: view.targetName, Negocio: businessName })}</p> : null}
      {view.kind === "expired" ? <p className="text-[14px] leading-relaxed">{text(copy.expired, { Nombre: view.targetName })}</p> : null}
      {view.kind === "accepted" || view.kind === "cancelled" || view.kind === "declinedRecipient" ? <p className="text-[14px] leading-relaxed">{copy[view.kind]}</p> : null}
      {state.kind === "error" ? <p role="alert" className="text-[14px] leading-relaxed">{state.message}</p> : null}
    </div>
  </AdaptivePanel>;
}
