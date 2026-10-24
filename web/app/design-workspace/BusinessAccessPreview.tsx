"use client";

import { useCallback, useEffect, useId, useMemo, useState, useSyncExternalStore } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useBusiness } from "@/components/business-app/BusinessWorkspace";
import { primaryButtonClass } from "@/components/business-app/business-ui";
import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import AccessRolePicker from "./AccessRolePicker";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";
import { accessActionGuard, accessRoles, changeAccessPreview, invitationStorageKeys, readAccessPreview, seedAccessPreview, type AccessAction, type AccessRole, type PreviewActor, type PreviewPerson } from "./businessAccessPreviewState";

const changedEvent = "workspace-preview-access-changed";
const emptyStorage = { getItem: () => null, setItem: () => {} };
// eslint-disable-next-line no-restricted-syntax -- Development-only bridge to the existing invitation sketch keys; production uses the live access component.
const storage = () => typeof window === "undefined" ? emptyStorage : window.localStorage;
const announceChange = () => window.dispatchEvent(new Event(changedEvent));
const trashClass = "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-black/55 hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 dark:text-white/65 dark:hover:bg-white/5";

/** Development-only settings review. All edits share the invitation preview's browser store. */
export default function BusinessAccessPreview() {
  const { t } = useTranslation();
  const { chosen, bridge } = useBusiness();
  const businessId = chosen?.space_id ?? "";
  const memberEmail = bridge?.memberEmail;
  const memberRole = chosen?.role;
  const actor = useMemo<PreviewActor | null>(() => memberEmail && memberRole === "owner" ? {email: memberEmail, permission: "owner"} : null, [memberEmail, memberRole]);
  const keys = useMemo(() => invitationStorageKeys(businessId), [businessId]);
  const subscribe = useCallback((listener: () => void) => {
    window.addEventListener("storage", listener);window.addEventListener(changedEvent, listener);
    return () => {window.removeEventListener("storage", listener);window.removeEventListener(changedEvent, listener);};
  }, []);
  const readSnapshot = useCallback(() => `${storage().getItem(keys.draft) ?? ""}\n${storage().getItem(keys.guide) ?? ""}`, [keys]);
  const raw = useSyncExternalStore(subscribe, readSnapshot, () => "");
  const snapshot = useMemo(() => { void raw; return readAccessPreview(storage(), businessId, actor); }, [raw, businessId, actor]);
  const [inviting, setInviting] = useState(false);
  const [confirmation, setConfirmation] = useState<AccessAction | null>(null);
  const [notice, setNotice] = useState<{key:string;email:string} | null>(null);
  const id = useId();
  useEffect(() => { if (seedAccessPreview(storage(), businessId)) announceChange(); }, [businessId]);

  function act(action: AccessAction) {
    const reason = changeAccessPreview(storage(), businessId, actor, action);
    setNotice({key:reason ? `workspace_setup_preview.access_guard_${reason}` : `workspace_setup_preview.access_${action.kind}_saved`, email:action.email});
    announceChange();
  }
  function personRow(person: PreviewPerson) {
    const pending = person.status === "pending";
    const protectedReason = accessActionGuard(snapshot, actor, {kind:pending ? "cancel" : "remove",email:person.email});
    const controls = <div className="flex shrink-0 items-center gap-1" aria-describedby={protectedReason ? `${id}-guard-${person.email}` : undefined}>
      <AccessRolePicker variant="quiet" compact value={person.permission} disabled={Boolean(protectedReason)} label={t("workspace_setup_preview.access_role_for",{email:person.email})} options={accessRoles.filter(role => role !== "owner" || actor?.permission === "owner").map(role => ({value:role,label:t(`workspace_setup_preview.permission_${role}`),description:t(`workspace_setup_preview.permission_${role}_detail`)}))} onChange={value => act({kind:"role",email:person.email,permission:value as AccessRole})} />
      <span id={`${id}-role-${person.email}`} className="sr-only">{t(`workspace_setup_preview.permission_${person.permission}_detail`)}</span>
      <button type="button" className={trashClass} disabled={Boolean(protectedReason)} aria-label={t(pending ? "workspace_setup_preview.access_cancel_for" : "workspace_setup_preview.access_remove_for",{email:person.email})} onClick={() => setConfirmation({kind:pending ? "cancel" : "remove",email:person.email})}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
    </div>;
    return <li key={person.email} className="flex min-h-16 flex-col gap-1 rounded-lg px-2 py-2 hover:bg-black/[0.025] focus-within:bg-black/[0.025] sm:flex-row sm:items-center sm:gap-4 dark:hover:bg-white/[0.035] dark:focus-within:bg-white/[0.035]">
      <div className="flex min-w-0 flex-1 items-center gap-3">
        <Avatar size={32} status={pending ? "pending" : null} />
        <div className="min-w-0 flex-1">
          <p className="break-all text-[16px] text-[#172b26] dark:text-white">{person.email}{person.current ? <span className="ml-2 text-[14px] text-black/55 dark:text-white/65">{t("workspace_setup_preview.access_you")}</span> : null}</p>
          {pending ? <div className="flex flex-wrap items-center gap-x-3 text-[14px] text-[#56635e] dark:text-white/70"><span>{t("workspace_setup_preview.invite_pending")}</span><button type="button" className="min-h-11 rounded-md underline-offset-4 hover:underline focus-visible:outline-2" onClick={() => act({kind:"resend",email:person.email})}>{t("workspace_setup_preview.access_resend")}</button></div> : null}
          {protectedReason ? <span id={`${id}-guard-${person.email}`} className="sr-only">{t(`workspace_setup_preview.access_guard_${protectedReason}`)}</span> : null}
        </div>
      </div>
      <div className="self-end sm:self-auto">
        {protectedReason ? <Tooltip content={t(`workspace_setup_preview.access_guard_${protectedReason}`)} side="top"><span tabIndex={0} role="group" aria-label={t("workspace_setup_preview.access_role_for",{email:person.email})} aria-describedby={`${id}-guard-${person.email}`} className="inline-flex rounded-md focus-visible:outline-2 focus-visible:outline-offset-2">{controls}</span></Tooltip> : controls}
      </div>
    </li>;
  }
  return <section data-testid="business-access-preview" style={{maxWidth:896}} className="space-y-4">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t("workspace_setup_preview.access_members_title")}</h2>
      <button type="button" className={primaryButtonClass} disabled={!actor} onClick={() => setInviting(true)}><UserPlus className="h-4 w-4" aria-hidden="true" />{t("workspace_setup_preview.invite")}</button>
    </div>
    <ul>{snapshot.members.map(personRow)}</ul>
    <details className="border-t border-black/10 pt-1 dark:border-white/10">
      <summary className="min-h-11 cursor-pointer content-center rounded-md px-2 text-[14px] text-[#56635e] focus-visible:outline-2 dark:text-white/70">{t("workspace_setup_preview.access_pending_title")} · {snapshot.pending.length}</summary>
      {snapshot.pending.length ? <ul>{snapshot.pending.map(personRow)}</ul> : <p className="px-2 py-2 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.access_no_pending")}</p>}
    </details>
    <p role="status" className="text-[14px] text-[#56635e] dark:text-white/70">{notice ? t(notice.key,{email:notice.email}) : ""}</p>
    <ConfirmDialog isOpen={confirmation !== null} title={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel_title" : "workspace_setup_preview.access_remove_title", {email:confirmation?.email})} description={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel_detail" : "workspace_setup_preview.access_remove_detail")} confirmLabel={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel" : "workspace_setup_preview.access_remove")} cancelLabel={t("common.cancel")} onCancel={() => setConfirmation(null)} onConfirm={() => {if(confirmation)act(confirmation);setConfirmation(null);}} />
    {inviting ? <WorkspaceSetupPreview invitation onClose={() => {setInviting(false);announceChange();}} /> : null}
  </section>;
}
