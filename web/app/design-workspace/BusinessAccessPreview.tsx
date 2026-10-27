"use client";

import { useCallback, useEffect, useId, useMemo, useRef, useState, useSyncExternalStore } from "react";
import { Trash2, UserPlus } from "lucide-react";
import { useTranslation } from "react-i18next";
import { ConfirmDialog } from "@/components/ui/ConfirmDialog";
import { useBusiness } from "@/components/business-app/BusinessWorkspace";
import { primaryButtonClass } from "@/components/business-app/business-ui";
import { SURFACE_CARD } from "@/components/business-app/foundation/surfaces";
import { Avatar } from "@/components/ui/Avatar";
import { Tooltip } from "@/components/ui/Tooltip";
import AccessRolePicker from "./AccessRolePicker";
import WorkspaceSetupPreview from "./WorkspaceSetupPreview";
import { accessActionGuard, accessRoles, changeAccessPreview, invitationStorageKeys, readAccessPreview, seedAccessPreview, type AccessAction, type AccessRole, type PreviewActor, type PreviewPerson } from "./businessAccessPreviewState";
import { changeBusinessRole, getBusinessAccess, resendBusinessAccessInvite, revokeBusinessAccessGrant, revokeBusinessAccessInvite, type BusinessAccess } from "@/lib/business-api";
import BusinessInvitationForm from "@/components/business-app/BusinessInvitationForm";

const changedEvent = "workspace-preview-access-changed";
const emptyStorage = { getItem: () => null, setItem: () => {} };
// eslint-disable-next-line no-restricted-syntax -- Development-only bridge to the existing invitation sketch keys; production uses the live access component.
const storage = () => typeof window === "undefined" ? emptyStorage : window.localStorage;
const announceChange = () => window.dispatchEvent(new Event(changedEvent));
const trashClass = "flex h-11 w-11 shrink-0 items-center justify-center rounded-lg text-black/55 hover:bg-black/5 focus-visible:outline-2 focus-visible:outline-offset-2 disabled:cursor-not-allowed disabled:opacity-40 dark:text-white/65 dark:hover:bg-white/5";

export default function BusinessAccessPreview() {
  const {source}=useBusiness();
  return source.mode==="live"?<BusinessAccessLive/>:<BusinessAccessSketch/>;
}

function BusinessAccessLive(){
  const {t}=useTranslation();
  const {chosen,reload}=useBusiness();
  const [access,setAccess]=useState<BusinessAccess|null>(null);
  const [failed,setFailed]=useState(false);
  const [refused,setRefused]=useState(false);
  const [busy,setBusy]=useState(false);
  const [inviting,setInviting]=useState(false);
  const [confirmation,setConfirmation]=useState<{id:string;email:string;pending:boolean}|null>(null);
  const [notice,setNotice]=useState<string|null>(null);
  const [attempt,setAttempt]=useState(0);
  const mounted=useRef(true);
  useEffect(()=>{
    mounted.current=true;
    getBusinessAccess().then(value=>{if(mounted.current){setAccess(value);setFailed(false);}},error=>{if(mounted.current){setFailed(true);setRefused(error?.status===403||error?.status===404);}});
    return()=>{mounted.current=false;};
  },[attempt]);
  const act=async(work:()=>Promise<unknown>)=>{
    if(busy||refused)return;
    setBusy(true);setFailed(false);setNotice(null);
    try{
      await work();
      const saved=await getBusinessAccess();
      if(mounted.current){setAccess(saved);reload();}
    }catch(error){if(mounted.current){setFailed(true);const status=error&&typeof error==="object"&&"status" in error?error.status:null;if(status===403||status===404)setRefused(true);}}
    finally{if(mounted.current)setBusy(false);}
  };
  if(!access)return <section className={SURFACE_CARD}>{failed?<><p role="alert">{t(refused?"business.lifecycle.errors.business_unavailable":"business_access.error")}</p>{!refused?<button className={primaryButtonClass} onClick={()=>setAttempt(value=>value+1)}>{t("common.retry")}</button>:null}</>:<div className="h-40 animate-pulse rounded-item bg-black/5 dark:bg-white/10" aria-busy="true"/>}</section>;
  const personRow=(person:{id:string;email:string|null;role:AccessRole|undefined;pending:boolean;expired?:boolean})=>{
    const self=!person.pending&&person.id===chosen?.grant_id;
    const restricted=self||refused||!chosen?.permissions?.includes("manage")||(person.role==="owner"&&!chosen.permissions.includes("assign_owner"));
    const email=person.email??"-";
    return <li key={person.id} className="flex min-h-16 flex-col gap-1 rounded-lg px-2 py-2 hover:bg-black/[0.025] focus-within:bg-black/[0.025] sm:flex-row sm:items-center sm:gap-4 dark:hover:bg-white/[0.035] dark:focus-within:bg-white/[0.035]">
      <div className="flex min-w-0 flex-1 items-center gap-3"><Avatar size={32} status={person.pending?"pending":null}/><div className="min-w-0 flex-1"><p className="break-all text-[16px]">{email}{self?<span className="ml-2 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.access_you")}</span>:null}</p>{person.pending?<div className="flex flex-wrap items-center gap-x-3 text-[14px] text-[#56635e] dark:text-white/70"><span>{t(person.expired?"business_access.invitation_expired":"workspace_setup_preview.invite_pending")}</span>{!person.expired?<button type="button" className="min-h-11 rounded-md hover:underline" disabled={busy||restricted} onClick={()=>void act(()=>resendBusinessAccessInvite(person.id))}>{t("workspace_setup_preview.access_resend")}</button>:null}</div>:null}</div></div>
      <div className="flex shrink-0 items-center gap-1 self-end sm:self-auto"><AccessRolePicker variant="quiet" compact value={person.role??""} disabled={busy||restricted||person.pending||!person.role} label={t("workspace_setup_preview.access_role_for",{email})} options={accessRoles.filter(role=>role!=="owner"||chosen?.permissions?.includes("assign_owner")).map(value=>({value,label:t(`workspace_setup_preview.permission_${value}`),description:t(`workspace_setup_preview.permission_${value}_detail`)}))} onChange={role=>void act(async()=>{const result=await changeBusinessRole(person.id,role as AccessRole);if(mounted.current&&result.invites.some(invite=>invite.email===person.email&&invite.requested_role===role))setNotice("workspace_setup_preview.invite_pending_detail");})}/><button type="button" className={trashClass} disabled={busy||restricted} aria-label={t(person.pending?"workspace_setup_preview.access_cancel_for":"workspace_setup_preview.access_remove_for",{email})} onClick={()=>setConfirmation({id:person.id,email,pending:person.pending})}><Trash2 className="h-4 w-4"/></button></div>
    </li>;
  };
  return <section data-testid="business-access-preview" style={{maxWidth:896}} className={`${SURFACE_CARD} space-y-4`}>
    <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="font-display text-[21px] font-medium">{t("workspace_setup_preview.access_members_title")}</h2><button type="button" className={primaryButtonClass} disabled={busy||refused||!chosen?.permissions?.includes("manage")} onClick={()=>setInviting(true)}><UserPlus className="h-4 w-4"/>{t("workspace_setup_preview.invite")}</button></div>
    <ul>{access.grants.map(person=>personRow({...person,role:person.business_role,pending:false}))}</ul>
    <details className="border-t border-black/10 pt-1 dark:border-white/10"><summary className="min-h-11 cursor-pointer content-center rounded-md px-2 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.access_pending_title")}</summary>{access.invites.length?<ul>{access.invites.map(person=>personRow({...person,role:person.requested_role,pending:true,expired:person.state==="expired"}))}</ul>:<p className="px-2 py-2 text-[14px] text-[#56635e] dark:text-white/70">{t("workspace_setup_preview.access_no_pending")}</p>}</details>
    {failed?<p role="alert" className="text-[14px] text-[#9e2f39] dark:text-[#ec9aa0]">{t(refused?"business.lifecycle.errors.business_unavailable":"business_access.remove_error")}</p>:null}
    {notice?<p role="status" className="text-[14px] text-[#56635e] dark:text-white/70">{t(notice)}</p>:null}
    <ConfirmDialog isOpen={confirmation!==null} title={t(confirmation?.pending?"workspace_setup_preview.access_cancel_title":"workspace_setup_preview.access_remove_title",{email:confirmation?.email})} description={t(confirmation?.pending?"workspace_setup_preview.access_cancel_detail":"workspace_setup_preview.access_remove_detail")} confirmLabel={t(confirmation?.pending?"workspace_setup_preview.access_cancel":"workspace_setup_preview.access_remove")} cancelLabel={t("common.cancel")} onCancel={()=>setConfirmation(null)} onConfirm={()=>{if(confirmation){const target=confirmation;setConfirmation(null);void act(()=>target.pending?revokeBusinessAccessInvite(target.id):revokeBusinessAccessGrant(target.id));}}}/>
    {inviting?<BusinessInvitationForm onClose={()=>setInviting(false)} onAccepted={()=>setAttempt(value=>value+1)}/>:null}
  </section>;
}

function BusinessAccessSketch() {
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
  return <section data-testid="business-access-preview" style={{maxWidth:896}} className={`${SURFACE_CARD} space-y-4`}>
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
