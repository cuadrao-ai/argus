"use client";
import { useEffect, useRef, useState } from "react";
import { Trash2, Plus } from "lucide-react";
import { useTranslation } from "react-i18next";
import AdaptivePanel from "@/components/ui/AdaptivePanel";
import { FormField } from "@/components/ui/FormField";
import AccessRolePicker from "@/app/design-workspace/AccessRolePicker";
import { accessRoles } from "@/app/design-workspace/businessAccessPreviewState";
import { inviteBusinessMembers, type BusinessInvitationCommand, type BusinessInvitationResult } from "@/lib/business-api";
import { primaryButtonClass, quietButtonClass } from "./business-ui";
import { useBusiness } from "./BusinessWorkspace";

type Row = BusinessInvitationCommand & { id:string; result?:BusinessInvitationResult };
const emptyRow=():Row=>({id:crypto.randomUUID(),email:"",role:"editor",command_key:crypto.randomUUID()});
/** The approved invitation rows, with server results replacing the browser sketch. */
export default function BusinessInvitationForm({onClose,onAccepted}:{onClose:()=>void;onAccepted:()=>void}) {
  const {t}=useTranslation();
  const {chosen}=useBusiness();
  const [rows,setRows]=useState<Row[]>([emptyRow()]);
  const [busy,setBusy]=useState(false);
  const [attempted,setAttempted]=useState(false);
  const [failed,setFailed]=useState(false);
  const [refused,setRefused]=useState(false);
  const mounted=useRef(true);
  useEffect(()=>{mounted.current=true;return()=>{mounted.current=false;};},[]);
  const errors=(row:Row)=>!/^\S+@[^\s@]+\.[^\s@]+$/.test(row.email.trim())||rows.some(other=>other!==row&&other.email.trim().toLowerCase()===row.email.trim().toLowerCase());
  const change=(key:string,patch:Partial<Row>)=>setRows(current=>current.map(row=>row.command_key===key?{...row,...patch,command_key:crypto.randomUUID()}:row));
  const submit=async()=>{
    if(busy||refused)return;
    setAttempted(true);
    const pending=rows.filter(row=>!row.result);
    if(pending.some(errors)||!pending.length)return;
    setBusy(true);setFailed(false);
    try {
      const response=await inviteBusinessMembers(pending.map(({email,role,command_key})=>({email:email.trim(),role,command_key})));
      if(!mounted.current)return;
      setRows(current=>current.map(row=>{const result=response.results.find(result=>result.command_key===row.command_key);return result?{...row,result}:row;}));
      onAccepted();
    }catch(error){if(mounted.current){setFailed(true);const status=error&&typeof error==="object"&&"status" in error?error.status:null;setRefused(status===403||status===404);}}
    finally{if(mounted.current)setBusy(false);}
  };
  return <AdaptivePanel title={t("workspace_setup_preview.batch_title")} summary={chosen?.name} width="lg" closeLabel={t("common.close")} onClose={()=>{if(!busy){mounted.current=false;onClose();}}} snaps={["full"]} initialSnap="full">
    <form noValidate className="p-5" onSubmit={event=>{event.preventDefault();void submit();}}>
      <ul aria-label={t("workspace_setup_preview.batch_recipients")}>
        {rows.map(row=><li key={row.id} className="py-2">
          {row.result ? <div><p className="break-all text-[16px]">{row.email} · {t(`workspace_setup_preview.permission_${row.role}`)}</p><p role={row.result.state==="refused"?"alert":"status"} className="mt-1 text-[14px] text-[#56635e]">{t(row.result.state==="pending"?"workspace_setup_preview.invite_pending_detail":row.result.state==="already_member"?"workspace_setup_preview.batch_member":"workspace_setup_preview.batch_send_error")}</p>{row.result.delivery && row.result.delivery!=="pending" ? <p className="text-[14px]">{t(`business_access.delivery_${row.result.delivery}`)}</p>:null}</div> : <div className="grid grid-cols-[minmax(0,1fr)_44px] items-end gap-2 sm:grid-cols-[minmax(0,1fr)_170px_44px]">
            <div className="col-span-2 sm:col-span-1"><FormField id={`invite-${row.command_key}`} label={t("workspace_setup_preview.invite_email_label")} type="email" autoComplete="email" value={row.email} disabled={busy||refused} error={attempted&&errors(row)?t("business_access.invalid_email"):null} onChange={event=>change(row.command_key,{email:event.target.value})}/></div>
            <AccessRolePicker compact value={row.role} label={t("workspace_setup_preview.permission_label")} disabled={busy||refused} options={accessRoles.filter(role=>role!=="owner"||chosen?.permissions?.includes("assign_owner")).map(value=>({value,label:t(`workspace_setup_preview.permission_${value}`),description:t(`workspace_setup_preview.permission_${value}_detail`)}))} onChange={role=>{if(accessRoles.includes(role as Row["role"]))change(row.command_key,{role:role as Row["role"]});}}/>
            <button type="button" className="flex h-11 w-11 items-center justify-center rounded-item" disabled={busy||refused} aria-label={t("workspace_setup_preview.batch_remove",{email:row.email})} onClick={()=>setRows(current=>current.filter(item=>item!==row))}><Trash2 className="h-4 w-4"/></button>
          </div>}
        </li>)}
      </ul>
      <button type="button" className={`${quietButtonClass} ml-auto`} disabled={busy||refused||rows.length>=50} onClick={()=>setRows(current=>[...current,emptyRow()])}><Plus className="h-4 w-4"/>{t("workspace_setup_preview.batch_add_short")}</button>
      {failed?<p role="alert" className="mt-3 text-[14px] text-[#9e2f39]">{t(refused?"business.lifecycle.errors.business_unavailable":"workspace_setup_preview.batch_send_error")}</p>:null}
      <div className="mt-6 border-t border-[#DCE0DA] pt-5"><button className={`${primaryButtonClass} w-full`} type="submit" disabled={busy||refused||rows.every(row=>row.result)}>{t(failed?"workspace_setup_preview.batch_retry":"workspace_setup_preview.batch_send")}</button></div>
    </form>
  </AdaptivePanel>;
}
