"use client";

import { useCallback, useEffect, useId, useMemo, useState, useSyncExternalStore } from "react";
import { ChevronDown, Trash2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useBusiness } from "@/components/business-app/BusinessWorkspace";
import { primaryButtonClass } from "@/components/business-app/business-ui";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";
import { accessActionGuard, accessRoles, changeAccessPreview, invitationStorageKeys, readAccessPreview, seedAccessPreview, type AccessAction, type AccessRole, type PreviewActor } from "./businessAccessPreviewState";

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
  return <section data-testid="business-access-preview" style={{maxWidth:896}} className="space-y-6">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h2 className="font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t("workspace_setup_preview.access_members_title")}</h2>
      <button type="button" className={primaryButtonClass} disabled={!actor} onClick={() => setInviting(true)}><UserPlus className="h-4 w-4" aria-hidden="true" />{t("workspace_setup_preview.invite")}</button>
    </div>
    <div className={SURFACE_CARD} style={{padding:12}}>
      <ul className="divide-y divide-black/5 dark:divide-white/10">
        {snapshot.members.map(person => {
          const protectedReason = accessActionGuard(snapshot, actor, {kind:"remove",email:person.email});
          const label = t("workspace_setup_preview.access_role_for", {email: person.email});
          return <li key={person.email} className="flex flex-col gap-2 px-2 py-3 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1"><p className="break-all text-[16px] text-[#172b26] dark:text-white">{person.email}{person.current ? <span className="ml-2 text-[14px] text-black/55 dark:text-white/65">{t("workspace_setup_preview.access_you")}</span> : null}</p>
              {protectedReason ? <p id={`${id}-guard-${person.email}`} className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t(`workspace_setup_preview.access_guard_${protectedReason}`)}</p> : null}
            </div>
            <div className="flex items-center gap-2 self-start sm:self-auto">
              <div className="relative"><select style={{minWidth:160,paddingRight:36,minHeight:44}} aria-label={label} aria-describedby={`${id}-role-${person.email}${protectedReason ? ` ${id}-guard-${person.email}` : ""}`} value={person.permission} disabled={Boolean(protectedReason)} onChange={event => act({kind:"role",email:person.email,permission:event.target.value as AccessRole})} className="min-h-11 appearance-none rounded-lg border border-black/15 bg-transparent py-2 pl-3 pr-9 text-[16px] text-[#172b26] disabled:cursor-not-allowed disabled:opacity-60 dark:border-white/20 dark:text-white">
                {accessRoles.filter(role => role !== "owner" || actor?.permission === "owner").map(role => <option key={role} value={role}>{t(`workspace_setup_preview.permission_${role}`)}</option>)}
              </select><ChevronDown aria-hidden="true" style={{position:"absolute",right:12,top:"50%",transform:"translateY(-50%)"}} className="pointer-events-none h-4 w-4 text-black/55 dark:text-white/65" /></div>
              <span id={`${id}-role-${person.email}`} className="sr-only">{t(`workspace_setup_preview.permission_${person.permission}_detail`)}</span>
              <button type="button" className={trashClass} disabled={Boolean(protectedReason)} aria-label={t("workspace_setup_preview.access_remove_for", {email:person.email})} onClick={() => setConfirmation({kind:"remove",email:person.email})}><Trash2 className="h-4 w-4" aria-hidden="true" /></button>
            </div>
          </li>;
        })}
      </ul>
    </div>
    <section>
      <h3 className="mb-3 font-display text-[21px] font-medium text-[#172b26] dark:text-white">{t("workspace_setup_preview.access_pending_title")}</h3>
      <div className={SURFACE_CARD} style={{padding:12}}>
        {snapshot.pending.length ? <ul className="divide-y divide-black/5 dark:divide-white/10">{snapshot.pending.map(person => <li key={person.email} className="flex flex-col gap-3 px-2 py-3 sm:flex-row sm:items-center sm:gap-4">
          <div className="min-w-0 flex-1"><p className="break-all text-[16px] text-[#172b26] dark:text-white">{person.email}</p><p className="mt-1 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.invite_pending")}</p><button type="button" className="min-h-11 rounded-lg text-[14px] text-[#56635e] underline-offset-4 hover:underline dark:text-white/70" onClick={() => act({kind:"resend",email:person.email})}>{t("workspace_setup_preview.access_resend")}</button></div>
          <div className="flex items-center gap-2 self-start sm:self-auto">
            <div className="relative"><select style={{minWidth:160,paddingRight:36,minHeight:44}} aria-label={t("workspace_setup_preview.access_role_for",{email:person.email})} value={person.permission} disabled={Boolean(accessActionGuard(snapshot,actor,{kind:"role",email:person.email,permission:person.permission}))} onChange={event => act({kind:"role",email:person.email,permission:event.target.value as AccessRole})} className="min-h-11 appearance-none rounded-lg border border-black/15 bg-transparent py-2 pl-3 pr-9 text-[16px] text-[#172b26] disabled:opacity-60 dark:border-white/20 dark:text-white">
              {accessRoles.filter(role => role !== "owner" || actor?.permission === "owner").map(role => <option key={role} value={role}>{t(`workspace_setup_preview.permission_${role}`)}</option>)}
            </select><ChevronDown aria-hidden="true" style={{position:"absolute",right:12,top:"50%",transform:"translateY(-50%)"}} className="pointer-events-none h-4 w-4 text-black/55 dark:text-white/65" /></div>
            <button type="button" className={trashClass} aria-label={t("workspace_setup_preview.access_cancel_for",{email:person.email})} onClick={() => setConfirmation({kind:"cancel",email:person.email})}><Trash2 className="h-4 w-4" aria-hidden="true" /></button></div>
        </li>)}</ul> : <p className="px-2 py-3 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.access_no_pending")}</p>}
      </div>
    </section>
    <p role="status" className="text-[14px] text-[#56635e] dark:text-white/70">{notice ? t(notice.key,{email:notice.email}) : ""}</p>
    <ConfirmDialog isOpen={confirmation !== null} title={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel_title" : "workspace_setup_preview.access_remove_title", {email:confirmation?.email})} description={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel_detail" : "workspace_setup_preview.access_remove_detail")} confirmLabel={t(confirmation?.kind === "cancel" ? "workspace_setup_preview.access_cancel" : "workspace_setup_preview.access_remove")} cancelLabel={t("common.cancel")} onCancel={() => setConfirmation(null)} onConfirm={() => {if(confirmation)act(confirmation);setConfirmation(null);}} />
    {inviting ? <WorkspaceSetupPreview invitation onClose={() => {setInviting(false);announceChange();}} /> : null}
  </section>;
}
